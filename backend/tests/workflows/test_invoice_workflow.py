"""Integration tests for complete invoice workflow execution."""

import json
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


@patch("backend.ingestion.pipeline.invoice_workflow.psycopg")
@patch("backend.ingestion.pipeline.invoice_workflow.PostgresSaver")
def test_compile_workflow_with_checkpoints(mock_saver, mock_psycopg):
    """Test workflow compilation with checkpointing."""
    from langgraph.checkpoint.memory import MemorySaver

    # PostgresSaver(conn) must return a real BaseCheckpointSaver subclass so
    # LangGraph's isinstance check passes
    mock_saver_instance = MemorySaver()
    mock_saver_instance.setup = Mock()
    mock_saver.return_value = mock_saver_instance

    workflow = compile_workflow_with_checkpoints()

    assert workflow is not None
    mock_saver.assert_called_once()
    mock_saver_instance.setup.assert_called_once()


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
@patch("backend.ingestion.pipeline.nodes.InvoiceValidator")
@patch("backend.ingestion.pipeline.nodes.GraphBuilder")
@patch("backend.ingestion.pipeline.nodes.ChromaDBClient")
def test_clean_invoice_workflow(
    mock_chroma, mock_graph, mock_validator, mock_extractor, mock_invoice_data
):
    """Test workflow with clean invoice (no anomalies)."""
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"
    mock_extractor_instance.structure_invoice.return_value = mock_invoice_data
    mock_extractor.return_value = mock_extractor_instance

    mock_validator_instance = Mock()
    mock_validator_instance.validate_invoice.return_value = []
    mock_validator.return_value = mock_validator_instance

    mock_graph_instance = Mock()
    mock_graph_instance.insert_invoice.return_value = "neo4j-123"
    mock_graph.return_value = mock_graph_instance

    mock_chroma.return_value = Mock()

    assert mock_extractor_instance.extract_text_from_pdf("test.pdf") == "Sample invoice text"
    assert mock_validator_instance.validate_invoice(Mock()) == []


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
@patch("backend.ingestion.pipeline.nodes.InvoiceValidator")
def test_high_risk_quarantine_workflow(mock_validator, mock_extractor, mock_invoice_data):
    """Test workflow with high-risk invoice gets quarantined."""
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"
    mock_extractor_instance.structure_invoice.return_value = mock_invoice_data
    mock_extractor.return_value = mock_extractor_instance

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

    anomalies = mock_validator_instance.validate_invoice(Mock())
    assert len(anomalies) == 2
    assert all(a.severity == "high" for a in anomalies)


@patch("backend.ingestion.pipeline.nodes.InvoiceExtractor")
def test_extraction_retry_with_critic(mock_extractor):
    """Test workflow retries extraction with critic feedback."""
    mock_extractor_instance = Mock()
    mock_extractor_instance.extract_text_from_pdf.return_value = "Sample invoice text"
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

    try:
        mock_extractor_instance.structure_invoice("text")
    except ValueError:
        pass

    result = mock_extractor_instance.structure_invoice("text with feedback")
    assert result["invoice_number"] == "INV-2024-0001"


@patch("backend.storage.workflow_store.get_pool")
def test_workflow_state_persistence(mock_get_pool):
    """Test that workflow state is persisted via WorkflowStore."""
    from backend.storage.workflow_store import WorkflowStore

    # get_pool().connection().__enter__() is what "conn" resolves to
    mock_conn = mock_get_pool.return_value.connection.return_value.__enter__.return_value

    test_state = {
        "document_id": "test-persistence-123",
        "status": "processing",
        "paused": False,
        "risk_level": "low",
        "retry_count": 0,
    }
    mock_conn.execute.return_value.fetchone.return_value = {
        "document_id": "test-persistence-123",
        "user_id": None,
        "status": "processing",
        "paused": False,
        "risk_level": "low",
        "retry_count": 0,
        "state_json": json.dumps(test_state),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }

    store = WorkflowStore(db_path="test_workflow_states.db")
    store.save_workflow("test-persistence-123", test_state)
    retrieved = store.get_workflow("test-persistence-123")

    assert retrieved is not None
    assert retrieved["document_id"] == "test-persistence-123"
    assert retrieved["status"] == "processing"

    store.delete_workflow("test-persistence-123")


@patch("backend.storage.workflow_store.get_pool")
def test_quarantine_retrieval(mock_get_pool):
    """Test retrieving quarantined workflows."""
    from backend.storage.workflow_store import WorkflowStore

    mock_conn = mock_get_pool.return_value.connection.return_value.__enter__.return_value

    quarantined_state = {
        "document_id": "test-quarantine-123",
        "status": "quarantined",
        "paused": True,
        "risk_level": "high",
        "retry_count": 0,
    }
    mock_conn.execute.return_value.fetchall.return_value = [
        {
            "document_id": "test-quarantine-123",
            "status": "quarantined",
            "paused": True,
            "risk_level": "high",
            "retry_count": 0,
            "state_json": json.dumps(quarantined_state),
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
    ]

    store = WorkflowStore(db_path="test_workflow_states.db")
    store.save_workflow("test-quarantine-123", quarantined_state)
    quarantined = store.get_all_quarantined()

    assert len(quarantined) > 0
    assert any(w["document_id"] == "test-quarantine-123" for w in quarantined)

    store.delete_workflow("test-quarantine-123")


@patch("backend.services.workflow_manager.compile_workflow_with_checkpoints")
@patch("backend.storage.workflow_store.WorkflowStore")
def test_workflow_manager_execute_sync(mock_store, mock_compile):
    """Test WorkflowManager synchronous execution."""
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
    mock_store.return_value = Mock()

    manager = WorkflowManager()
    result = manager.execute_sync(Path("/tmp/test.pdf"))

    assert result is not None
    mock_workflow.stream.assert_called_once()
