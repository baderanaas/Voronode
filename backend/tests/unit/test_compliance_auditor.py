"""
Unit tests for Contract Compliance Auditor.

Tests all validation rules:
- Retention rate calculation
- Unit price validation
- Billing cap enforcement
- Scope validation (approved cost codes)
"""

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import Mock, MagicMock

from backend.ingestion.compliance_auditor import ContractComplianceAuditor
from backend.core.models import Invoice, LineItem, Contract


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client for testing."""
    client = MagicMock()
    return client


@pytest.fixture
def compliance_auditor(mock_neo4j_client):
    """Create compliance auditor instance."""
    return ContractComplianceAuditor(mock_neo4j_client)


@pytest.fixture
def sample_invoice():
    """Create a sample invoice for testing."""
    return Invoice(
        id="INV-001",
        invoice_number="INV-2024-001",
        date=date(2024, 1, 15),
        contractor_id="CONT-001",
        contract_id="CONTRACT-001",
        amount=Decimal("100000.00"),
        line_items=[
            LineItem(
                description="Concrete work",
                quantity=Decimal("100"),
                unit_price=Decimal("500"),
                total=Decimal("50000"),
                cost_code="03-100",
            ),
            LineItem(
                description="Steel framing",
                quantity=Decimal("200"),
                unit_price=Decimal("250"),
                total=Decimal("50000"),
                cost_code="05-200",
            ),
        ],
    )


@pytest.fixture
def sample_contract():
    """Create a sample contract for testing."""
    return {
        "contract_id": "CONTRACT-001",
        "retention_rate": "0.10",
        "value": "500000.00",
        "unit_price_schedule": {
            "03-100": "550.00",  # Concrete max price
            "05-200": "275.00",  # Steel max price
        },
        "approved_cost_codes": ["03-100", "05-200", "09-100"],
    }


class TestComplianceAuditorBasics:
    """Test basic compliance auditor functionality."""

    def test_audit_invoice_without_contract_id(self, compliance_auditor):
        """Test that invoice without contract_id returns missing contract anomaly."""
        invoice = Invoice(
            invoice_number="INV-001",
            date=date(2024, 1, 1),
            contractor_id="CONT-001",
            contract_id=None,  # No contract
            amount=Decimal("10000"),
        )

        anomalies = compliance_auditor.audit_invoice(invoice)

        assert len(anomalies) == 1
        assert anomalies[0].type == "missing_contract"
        assert anomalies[0].severity == "high"

    def test_audit_invoice_contract_not_found(
        self, compliance_auditor, sample_invoice, mock_neo4j_client
    ):
        """Test that non-existent contract returns contract_not_found anomaly."""
        # Mock Neo4j to return no contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = None
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        assert len(anomalies) == 1
        assert anomalies[0].type == "contract_not_found"
        assert anomalies[0].severity == "critical"


class TestRetentionValidation:
    """Test retention rate validation."""

    def test_retention_correct(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that correct retention passes validation."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Add retention line item (10% of 100000 = 10000)
        # The auditor sums totals of items with "retention" in description,
        # so the value should match expected_retention (positive amount withheld)
        sample_invoice.line_items.append(
            LineItem(
                description="Retention (10%)",
                quantity=Decimal("1"),
                unit_price=Decimal("10000"),
                total=Decimal("10000"),
                cost_code="99-RET",
            )
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have no retention violations
        retention_anomalies = [a for a in anomalies if a.type == "retention_violation"]
        assert len(retention_anomalies) == 0

    def test_retention_incorrect(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that incorrect retention amount triggers anomaly."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Add WRONG retention (should be 10000, but only 5000)
        sample_invoice.line_items.append(
            LineItem(
                description="Retention",
                quantity=Decimal("1"),
                unit_price=Decimal("-5000"),
                total=Decimal("-5000"),
                cost_code="99-RET",
            )
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have retention violation
        retention_anomalies = [a for a in anomalies if a.type == "retention_violation"]
        assert len(retention_anomalies) == 1
        assert retention_anomalies[0].severity in ["medium", "high"]

    def test_retention_zero_rate(
        self, compliance_auditor, sample_invoice, mock_neo4j_client
    ):
        """Test that 0% retention rate works correctly."""
        contract = {
            "contract_id": "CONTRACT-001",
            "retention_rate": "0.00",  # No retention
            "value": "500000.00",
            "unit_price_schedule": {},
            "approved_cost_codes": ["03-100", "05-200"],
        }

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have no retention violations (expected 0, actual 0)
        retention_anomalies = [a for a in anomalies if a.type == "retention_violation"]
        assert len(retention_anomalies) == 0


class TestUnitPriceValidation:
    """Test unit price validation against contract schedule."""

    def test_unit_price_within_limit(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that unit prices within contract limits pass."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Unit prices are within limits (500 < 550, 250 < 275)
        price_anomalies = [a for a in anomalies if a.type == "price_mismatch"]
        assert len(price_anomalies) == 0

    def test_unit_price_exceeds_limit(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that unit prices exceeding limits trigger anomalies."""
        # Modify invoice to have higher unit prices
        sample_invoice.line_items[0].unit_price = Decimal("700")  # Exceeds 550 limit
        sample_invoice.line_items[0].total = Decimal("70000")

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have price mismatch
        price_anomalies = [a for a in anomalies if a.type == "price_mismatch"]
        assert len(price_anomalies) >= 1
        assert price_anomalies[0].severity in ["medium", "high", "critical"]
        assert price_anomalies[0].cost_code == "03-100"

    def test_unit_price_within_tolerance(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that prices within tolerance (5%) are accepted."""
        # Set price just within 5% tolerance (550 * 1.05 = 577.5)
        sample_invoice.line_items[0].unit_price = Decimal("575")
        sample_invoice.line_items[0].total = Decimal("57500")

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should pass (within 5% tolerance)
        price_anomalies = [a for a in anomalies if a.type == "price_mismatch"]
        assert len(price_anomalies) == 0


class TestBillingCapValidation:
    """Test billing cap enforcement."""

    def test_billing_cap_not_exceeded(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that invoices under billing cap pass."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}

        # Mock total billed: 200k already billed, + 100k this invoice = 300k < 500k cap
        total_billed_mock = MagicMock()
        total_billed_mock.single.return_value = {"total_billed": 200000}

        session_mock.run.side_effect = [result_mock, total_billed_mock]
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should not exceed cap
        cap_anomalies = [a for a in anomalies if a.type == "billing_cap_exceeded"]
        assert len(cap_anomalies) == 0

    def test_billing_cap_exceeded(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that invoices exceeding billing cap trigger anomaly."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}

        # Mock total billed: 450k already billed, + 100k this invoice = 550k > 500k cap
        total_billed_mock = MagicMock()
        total_billed_mock.single.return_value = {"total_billed": 450000}

        session_mock.run.side_effect = [result_mock, total_billed_mock]
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should exceed cap
        cap_anomalies = [a for a in anomalies if a.type == "billing_cap_exceeded"]
        assert len(cap_anomalies) == 1
        assert cap_anomalies[0].severity in ["high", "critical"]

    def test_billing_cap_at_limit(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test invoice exactly at billing cap."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}

        # Mock total billed: 400k already billed, + 100k this invoice = 500k = 500k cap
        total_billed_mock = MagicMock()
        total_billed_mock.single.return_value = {"total_billed": 400000}

        session_mock.run.side_effect = [result_mock, total_billed_mock]
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should not exceed cap (exactly at limit is OK)
        cap_anomalies = [a for a in anomalies if a.type == "billing_cap_exceeded"]
        assert len(cap_anomalies) == 0

    def test_no_billing_cap_defined(
        self, compliance_auditor, sample_invoice, mock_neo4j_client
    ):
        """Test that missing billing cap skips validation."""
        contract = {
            "contract_id": "CONTRACT-001",
            "retention_rate": "0.10",
            "value": None,  # No billing cap
            "unit_price_schedule": {},
            "approved_cost_codes": ["03-100", "05-200"],
        }

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should not have cap violations (no cap to violate)
        cap_anomalies = [a for a in anomalies if a.type == "billing_cap_exceeded"]
        assert len(cap_anomalies) == 0


class TestScopeValidation:
    """Test scope validation (approved cost codes)."""

    def test_all_cost_codes_approved(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that all approved cost codes pass validation."""
        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # All cost codes are approved (03-100, 05-200)
        scope_anomalies = [a for a in anomalies if a.type == "scope_violation"]
        assert len(scope_anomalies) == 0

    def test_unapproved_cost_code(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test that unapproved cost codes trigger violations."""
        # Add line item with unapproved cost code
        sample_invoice.line_items.append(
            LineItem(
                description="Unauthorized electrical work",
                quantity=Decimal("10"),
                unit_price=Decimal("1000"),
                total=Decimal("10000"),
                cost_code="16-500",  # NOT in approved list
            )
        )

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have scope violation
        scope_anomalies = [a for a in anomalies if a.type == "scope_violation"]
        assert len(scope_anomalies) == 1
        assert scope_anomalies[0].severity == "high"
        assert scope_anomalies[0].cost_code == "16-500"

    def test_no_approved_cost_codes_defined(
        self, compliance_auditor, sample_invoice, mock_neo4j_client
    ):
        """Test that missing approved cost codes list skips validation."""
        contract = {
            "contract_id": "CONTRACT-001",
            "retention_rate": "0.10",
            "value": "500000.00",
            "unit_price_schedule": {},
            "approved_cost_codes": [],  # Empty list
        }

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should not have scope violations (no approved list to check against)
        scope_anomalies = [a for a in anomalies if a.type == "scope_violation"]
        assert len(scope_anomalies) == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invoice_with_no_line_items(
        self, compliance_auditor, sample_contract, mock_neo4j_client
    ):
        """Test invoice with no line items."""
        invoice = Invoice(
            invoice_number="INV-001",
            date=date(2024, 1, 1),
            contractor_id="CONT-001",
            contract_id="CONTRACT-001",
            amount=Decimal("10000"),
            line_items=[],  # No line items
        )

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}
        session_mock.run.return_value = result_mock
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        # Mock total billed query
        session_mock.run.side_effect = [
            result_mock,  # First call: get contract
            MagicMock(single=lambda: {"total_billed": 0}),  # Second call: total billed
        ]

        # Should not crash
        anomalies = compliance_auditor.audit_invoice(invoice)
        assert isinstance(anomalies, list)

    def test_multiple_violations_same_invoice(
        self, compliance_auditor, sample_invoice, sample_contract, mock_neo4j_client
    ):
        """Test invoice with multiple compliance violations."""
        # Modify invoice to have multiple violations
        sample_invoice.line_items[0].unit_price = Decimal("700")  # Price violation
        sample_invoice.line_items.append(
            LineItem(
                description="Out of scope work",
                quantity=Decimal("10"),
                unit_price=Decimal("1000"),
                total=Decimal("10000"),
                cost_code="99-999",  # Scope violation
            )
        )

        # Mock Neo4j to return contract
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.single.return_value = {"c": sample_contract}

        # Mock total billed to exceed cap
        total_billed_mock = MagicMock()
        total_billed_mock.single.return_value = {"total_billed": 450000}

        session_mock.run.side_effect = [result_mock, total_billed_mock]
        mock_neo4j_client.driver.session.return_value.__enter__.return_value = (
            session_mock
        )

        anomalies = compliance_auditor.audit_invoice(sample_invoice)

        # Should have multiple violations
        assert len(anomalies) >= 2
        types = [a.type for a in anomalies]
        assert "price_mismatch" in types
        assert "scope_violation" in types
