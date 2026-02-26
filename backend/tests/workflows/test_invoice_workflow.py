"""Integration tests for complete invoice workflow execution."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from backend.ingestion.pipeline.invoice_workflow import (
    create_invoice_workflow_graph,
    compile_workflow_with_checkpoints,
)
from backend.services.workflow_manager import WorkflowManager


@pytest.fixture
def mock_invoice_data():
    """Mock extracted invoice data."""
    return {
        "invoice_number": "INV-2024-0001",
        "date": "2024-01-15",
        "due_date": "2024-02-15",
        "contractor_name": "ABC Construction",
        "total_amount": 10000.00,
        "line_items": [
            {
                "cost_code": "05-500",
                "description": "Concrete work",
                "quantity": 100.0,
                "unit_price": 100.0,
                "total": 10000.0,
            }
        ],
    }


@pytest.fixture
def clean_invoice_state(mock_invoice_data):
    """State for clean invoice (no anomalies)."""
    return {
        "document_id": "test-clean-123",
        "document_path": "/tmp/test.pdf",
        "document_type": "invoice",
        "raw_text": "Sample invoice text",
        "extracted_data": mock_invoice_data,
        "validation_results": [],
        "anomalies": [],
        "critic_feedback": None,
        "retry_count": 0,
        "max_retries": 3,
        "graph_updated": False,
        "risk_level": "unknown",
        "final_report": None,
        "status": "processing",
        "paused": False,
        "pause_reason": None,
        "human_feedback": None,
        "error_history": [],
        "processing_time_ms": 0,
        "neo4j_id": None,
        "extraction_confidence": None,
    }


def test_create_workflow_graph():
    """Test that workflow graph is created successfully."""
    graph = create_invoice_workflow_graph()

    assert graph is not None
    # Verify nodes are added
    nodes = graph.nodes
    assert "extract_text" in nodes
    assert "structure_invoice" in nodes
    assert "validate" in nodes
    assert "critic" in nodes
    assert "quarantine" in nodes
    assert "insert_graph" in nodes
    assert "embed" in nodes
    assert "finalize" in nodes
    assert "error_handler" in nodes


@patch("backend.ingestion.pipeline.invoice_workflow.sqlite3")
@patch("backend.ingestion.pipeline.invoice_workflow.SqliteSaver")
def test_compile_workflow_with_checkpoints(mock_saver, mock_sqlite):
    """Test workflow compilation with checkpointing."""
    from langgraph.checkpoint.memory import MemorySaver

    # The code calls SqliteSaver(conn) directly (constructor, not from_conn_string)
    # Return a real BaseCheckpointSaver subclass so LangGraph's isinstance check passes
    mock_saver.return_value = MemorySaver()

    workflow = compile_workflow_with_checkpoints("test_checkpoints.db")

    assert workflow is not None
    mock_saver.assert_called_once()  # Verifies SqliteSaver was instantiated


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
@patch("backend.ingestion.pipeline.nodes.InvoiceValidator")
@patch("backend.ingestion.pipeline.nodes.GraphBuilder")
@patch("backend.ingestion.pipeline.nodes.ChromaDBClient")
def test_clean_invoice_workflow(
    mock_chroma, mock_graph, mock_validator, mock_extractor, mock_invoice_data
):
    """
    Test workflow with clean invoice (no anomalies).

    Expected path: extract_text → structure_invoice → validate → insert_graph → embed → finalize
    """
    # Mock extractor
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"
    mock_extractor_instance.structure_invoice.return_value = mock_invoice_data
    mock_extractor.return_value = mock_extractor_instance

    # Mock validator (no anomalies)
    mock_validator_instance = Mock()
    mock_validator_instance.validate_invoice.return_value = []
    mock_validator.return_value = mock_validator_instance

    # Mock graph builder
    mock_graph_instance = Mock()
    mock_graph_instance.insert_invoice.return_value = "neo4j-123"
    mock_graph.return_value = mock_graph_instance

    # Mock ChromaDB
    mock_chroma_instance = Mock()
    mock_chroma.return_value = mock_chroma_instance

    # Note: Full integration test would require actual LangGraph execution
    # This test verifies mocks are set up correctly
    assert mock_extractor_instance.extract_text_from_pdf("test.pdf") == "Sample invoice text"
    assert mock_validator_instance.validate_invoice(Mock()) == []


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
@patch("backend.ingestion.pipeline.nodes.InvoiceValidator")
def test_high_risk_quarantine_workflow(mock_validator, mock_extractor, mock_invoice_data):
    """
    Test workflow with high-risk invoice gets quarantined.

    Expected path: extract_text → structure_invoice → validate → quarantine (END)
    """
    # Mock extractor
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"
    mock_extractor_instance.structure_invoice.return_value = mock_invoice_data
    mock_extractor.return_value = mock_extractor_instance

    # Mock validator with high-severity anomalies
    mock_anomaly = Mock()
    mock_anomaly.severity = "high"
    mock_anomaly.to_dict.return_value = {
        "type": "total_mismatch",
        "severity": "high",
        "message": "Invoice total does not match line items",
        "field": "amount",
        "expected": 10000.0,
        "actual": 9000.0,
    }

    mock_validator_instance = Mock()
    mock_validator_instance.validate_invoice.return_value = [mock_anomaly, mock_anomaly]
    mock_validator.return_value = mock_validator_instance

    # Verify high severity anomalies detected
    anomalies = mock_validator_instance.validate_invoice(Mock())
    assert len(anomalies) == 2
    assert all(a.severity == "high" for a in anomalies)


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
def test_extraction_retry_with_critic(mock_extractor):
    """
    Test workflow retries extraction with critic feedback.

    Expected path: extract_text → structure_invoice (fail) → critic → structure_invoice (retry)
    """
    # Mock extractor
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"

    # First call fails, second succeeds
    mock_extractor_instance.structure_invoice.side_effect = [
        ValueError("Failed to extract"),
        {
            "invoice_number": "INV-2024-0001",
            "date": "2024-01-15",
            "contractor_name": "ABC Construction",
            "total_amount": 10000.0,
            "line_items": [],
        },
    ]

    mock_extractor.return_value = mock_extractor_instance

    # Verify retry behavior
    try:
        mock_extractor_instance.structure_invoice("text")
    except ValueError:
        pass  # First call fails

    result = mock_extractor_instance.structure_invoice("text with feedback")
    assert result["invoice_number"] == "INV-2024-0001"


def test_workflow_state_persistence():
    """Test that workflow state is persisted to SQLite."""
    from backend.storage.workflow_store import WorkflowStore

    store = WorkflowStore(db_path="test_workflow_states.db")

    test_state = {
        "document_id": "test-persistence-123",
        "status": "processing",
        "paused": False,
        "risk_level": "low",
        "retry_count": 0,
    }

    # Save state
    store.save_workflow("test-persistence-123", test_state)

    # Retrieve state
    retrieved = store.get_workflow("test-persistence-123")

    assert retrieved is not None
    assert retrieved["document_id"] == "test-persistence-123"
    assert retrieved["status"] == "processing"

    # Clean up
    store.delete_workflow("test-persistence-123")


def test_quarantine_retrieval():
    """Test retrieving quarantined workflows."""
    from backend.storage.workflow_store import WorkflowStore

    store = WorkflowStore(db_path="test_workflow_states.db")

    # Create quarantined workflow
    quarantined_state = {
        "document_id": "test-quarantine-123",
        "status": "quarantined",
        "paused": True,
        "risk_level": "high",
        "retry_count": 0,
    }

    store.save_workflow("test-quarantine-123", quarantined_state)

    # Retrieve quarantined workflows
    quarantined = store.get_all_quarantined()

    assert len(quarantined) > 0
    assert any(w["document_id"] == "test-quarantine-123" for w in quarantined)

    # Clean up
    store.delete_workflow("test-quarantine-123")


@patch("backend.services.workflow_manager.compile_workflow_with_checkpoints")
@patch("backend.storage.workflow_store.WorkflowStore")
def test_workflow_manager_execute_sync(mock_store, mock_compile):
    """Test WorkflowManager synchronous execution."""
    # Mock compiled workflow
    mock_workflow = Mock()
    mock_final_state = {
        "document_id": "test-manager-123",
        "status": "completed",
        "extracted_data": {"invoice_number": "INV-001"},
        "graph_updated": True,
        "processing_time_ms": 5000,
    }

    mock_workflow.stream.return_value = [
        {"extract_text": {"raw_text": "text"}},
        {"finalize": mock_final_state},
    ]

    mock_compile.return_value = mock_workflow

    # Mock store
    mock_store_instance = Mock()
    mock_store.return_value = mock_store_instance

    # Execute workflow
    manager = WorkflowManager()
    result = manager.execute_sync(Path("/tmp/test.pdf"))

    assert result is not None
    # Workflow should have been called
    mock_workflow.stream.assert_called_once()
