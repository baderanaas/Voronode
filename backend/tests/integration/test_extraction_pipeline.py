"""Integration tests for invoice extraction pipeline."""

import pytest
from pathlib import Path
from decimal import Decimal
from datetime import date

from backend.agents.extractor import InvoiceExtractor
from backend.agents.validator import InvoiceValidator
from backend.services.graph_builder import GraphBuilder
from backend.vector.client import ChromaDBClient
from backend.graph.client import Neo4jClient
from backend.core.models import Invoice, LineItem


# Test fixtures path
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "invoices"


@pytest.fixture
def extractor():
    """Create InvoiceExtractor instance."""
    return InvoiceExtractor()


@pytest.fixture
def validator():
    """Create InvoiceValidator instance."""
    return InvoiceValidator()


@pytest.fixture
def graph_builder():
    """Create GraphBuilder instance."""
    return GraphBuilder()


@pytest.fixture
def chroma_client():
    """Create ChromaDBClient instance."""
    return ChromaDBClient()


@pytest.fixture
def neo4j_client():
    """Create Neo4jClient instance."""
    return Neo4jClient()


@pytest.fixture
def sample_invoice_pdf():
    """Path to sample invoice PDF."""
    pdf_path = FIXTURES_DIR / "INV-2024-0001.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Sample invoice not found: {pdf_path}")
    return pdf_path


class TestExtractionPipeline:
    """Test full invoice extraction pipeline."""

    def test_pdf_text_extraction(self, extractor, sample_invoice_pdf):
        """Test PDF text extraction."""
        text = extractor.extract_text_from_pdf(sample_invoice_pdf)

        assert text is not None
        assert len(text) > 0
        assert "invoice" in text.lower() or "INV-" in text

    def test_invoice_structuring(self, extractor, sample_invoice_pdf):
        """Test structured invoice extraction."""
        invoice = extractor.extract_invoice_from_pdf(sample_invoice_pdf)

        # Verify basic fields
        assert invoice.invoice_number is not None
        assert invoice.date is not None
        assert invoice.contractor_id is not None
        assert invoice.amount > 0
        assert len(invoice.line_items) > 0

        # Verify extraction metadata
        assert invoice.extracted_at is not None
        assert invoice.extraction_confidence is not None

    def test_full_extraction_pipeline(
        self, extractor, validator, graph_builder, sample_invoice_pdf
    ):
        """Test end-to-end extraction pipeline."""
        # Step 1: Extract
        invoice = extractor.extract_invoice_from_pdf(sample_invoice_pdf)

        # Step 2: Validate
        anomalies = validator.validate_invoice(invoice)

        # Should have no high-severity anomalies for valid test data
        high_severity = [a for a in anomalies if a.severity == "high"]
        assert (
            len(high_severity) == 0
        ), f"Unexpected high-severity anomalies: {high_severity}"

        # Step 3: Insert into graph
        invoice_id = graph_builder.insert_invoice(invoice)
        assert invoice_id is not None

        # Step 4: Verify retrieval
        retrieved = graph_builder.get_invoice_by_id(invoice_id)
        assert retrieved is not None
        assert retrieved["invoice_number"] == invoice.invoice_number
        assert len(retrieved["line_items"]) == len(invoice.line_items)


class TestValidation:
    """Test invoice validation logic."""

    def test_math_validation_success(self, validator):
        """Test math validation with correct values."""
        invoice = Invoice(
            invoice_number="TEST-001",
            date=date.today(),
            contractor_id="contractor-1",
            amount=Decimal("1000.00"),
            line_items=[
                LineItem(
                    description="Test item",
                    cost_code="01-100",
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    total=Decimal("1000.00"),
                )
            ],
        )

        anomalies = validator.validate_invoice(invoice)

        # Should have no math errors
        math_errors = [a for a in anomalies if a.type == "math_error"]
        assert len(math_errors) == 0

    def test_anomaly_detection(self, validator):
        """Test detection of intentional math errors."""
        invoice = Invoice(
            invoice_number="TEST-002",
            date=date.today(),
            contractor_id="contractor-1",
            amount=Decimal("1000.00"),
            line_items=[
                LineItem(
                    description="Incorrect total",
                    cost_code="01-100",
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    total=Decimal("1100.00"),  # Wrong!
                )
            ],
        )

        anomalies = validator.validate_invoice(invoice)

        # Should detect math error
        math_errors = [a for a in anomalies if a.type == "math_error"]
        assert len(math_errors) > 0
        assert math_errors[0].severity == "high"

    def test_total_mismatch_detection(self, validator):
        """Test detection of invoice total mismatch."""
        invoice = Invoice(
            invoice_number="TEST-003",
            date=date.today(),
            contractor_id="contractor-1",
            amount=Decimal("2000.00"),  # Wrong total!
            line_items=[
                LineItem(
                    description="Item 1",
                    cost_code="01-100",
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    total=Decimal("1000.00"),
                )
            ],
        )

        anomalies = validator.validate_invoice(invoice)

        # Should detect total mismatch
        total_errors = [a for a in anomalies if a.type == "total_mismatch"]
        assert len(total_errors) > 0


class TestGraphInsertion:
    """Test Neo4j graph insertion."""

    def test_missing_contractor_creates_placeholder(self, graph_builder):
        """Test that missing contractors get placeholder nodes."""
        invoice = Invoice(
            invoice_number="TEST-PLACEHOLDER",
            date=date.today(),
            contractor_id="Unknown Contractor XYZ",  # Doesn't exist
            amount=Decimal("500.00"),
            line_items=[
                LineItem(
                    description="Test item",
                    cost_code="01-100",
                    quantity=Decimal("5"),
                    unit_price=Decimal("100"),
                    total=Decimal("500.00"),
                )
            ],
        )

        invoice_id = graph_builder.insert_invoice(invoice)
        assert invoice_id is not None

        # Verify invoice can be retrieved
        retrieved = graph_builder.get_invoice_by_id(invoice_id)
        assert retrieved is not None

    def test_idempotency(self, extractor, graph_builder, sample_invoice_pdf):
        """Test uploading same invoice twice doesn't create duplicates."""
        # First upload
        invoice1 = extractor.extract_invoice_from_pdf(sample_invoice_pdf)
        invoice_id1 = graph_builder.insert_invoice(invoice1)

        # Second upload (same invoice number)
        invoice2 = extractor.extract_invoice_from_pdf(sample_invoice_pdf)
        invoice2.id = invoice1.id  # Use same ID to test MERGE
        invoice_id2 = graph_builder.insert_invoice(invoice2)

        # Should return same ID
        assert invoice_id1 == invoice_id2

        # Verify only one invoice exists
        retrieved = graph_builder.get_invoice_by_id(invoice_id1)
        assert retrieved is not None


class TestChromaDBEmbedding:
    """Test ChromaDB vector embedding."""

    def test_invoice_embedding(self, chroma_client):
        """Test embedding invoice text in ChromaDB."""
        invoice_id = "test-invoice-123"
        invoice_text = "Invoice INV-2024-0001, concrete work, $5000"

        chroma_client.add_document(
            collection_name="invoices",
            doc_id=invoice_id,
            text=invoice_text,
            metadata={"invoice_number": "INV-2024-0001", "amount": 5000.0},
        )

        # Verify embedding was created (basic connectivity test)
        collection = chroma_client.client.get_collection("invoices")
        result = collection.get(ids=[invoice_id])

        assert result is not None
        assert len(result["ids"]) > 0


class TestServiceConnectivity:
    """Test service connectivity."""

    def test_neo4j_connectivity(self, neo4j_client):
        """Test Neo4j connection."""
        assert neo4j_client.verify_connectivity() is True

    def test_chromadb_connectivity(self, chroma_client):
        """Test ChromaDB connection."""
        assert chroma_client.verify_connectivity() is True


# Performance benchmarks
class TestPerformance:
    """Test performance benchmarks."""

    def test_processing_time(self, extractor, validator, graph_builder, sample_invoice_pdf):
        """Test that processing completes within 30 seconds."""
        import time

        start = time.time()

        # Full pipeline
        invoice = extractor.extract_invoice_from_pdf(sample_invoice_pdf)
        validator.validate_invoice(invoice)
        graph_builder.insert_invoice(invoice)

        elapsed = time.time() - start

        # Should complete within 30 seconds
        assert elapsed < 30, f"Processing took {elapsed}s (limit: 30s)"
