"""Unit tests for individual workflow nodes."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.ingestion.pipeline.nodes import (
    extract_text_node,
    structure_invoice_node,
    validate_invoice_node,
    critic_agent_node,
    quarantine_node,
    insert_graph_node,
    finalize_node,
    error_handler_node,
)
from backend.core.state import WorkflowState


def test_extract_text_node_success():
    """Test successful text extraction."""
    state = {
        "document_id": "test-123",
        "document_path": "test.pdf",
        "document_type": "invoice",
        "raw_text": None,
        "extracted_data": None,
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

    with patch("backend.ingestion.pipeline.nodes.InvoiceExtractor") as mock_extractor:
        mock_instance = Mock()
        mock_instance.extract_text_from_pdf.return_value = "Sample invoice text"
        mock_extractor.return_value = mock_instance

        result = extract_text_node(state)

        assert result["raw_text"] == "Sample invoice text"
        assert result["status"] == "processing"


def test_extract_text_node_failure():
    """Test text extraction failure handling."""
    state = {
        "document_id": "test-123",
        "document_path": "nonexistent.pdf",
        "document_type": "invoice",
        "raw_text": None,
        "extracted_data": None,
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

    with patch("backend.ingestion.pipeline.nodes.InvoiceExtractor") as mock_extractor:
        mock_instance = Mock()
        mock_instance.extract_text_from_pdf.side_effect = ValueError("File not found")
        mock_extractor.return_value = mock_instance

        result = extract_text_node(state)

        assert result["status"] == "failed"
        assert len(result["error_history"]) == 1
        assert "File not found" in result["error_history"][0]["error"]


def test_quarantine_node():
    """Test quarantine node pauses workflow."""
    state = {
        "document_id": "test-123",
        "risk_level": "high",
        "retry_count": 0,
        "max_retries": 3,
    }

    result = quarantine_node(state)

    assert result["paused"] is True
    assert result["status"] == "quarantined"
    assert "High risk level" in result["pause_reason"]


def test_quarantine_node_max_retries():
    """Test quarantine due to max retries."""
    state = {
        "document_id": "test-123",
        "risk_level": "medium",
        "retry_count": 3,
        "max_retries": 3,
    }

    result = quarantine_node(state)

    assert result["paused"] is True
    assert result["status"] == "quarantined"
    assert "Max retries" in result["pause_reason"]


def test_finalize_node():
    """Test finalize node generates report."""
    state = {
        "document_id": "test-123",
        "extracted_data": {"invoice_number": "INV-001"},
        "neo4j_id": "neo4j-123",
        "extraction_confidence": 0.95,
        "risk_level": "low",
        "anomalies": [],
        "retry_count": 0,
        "graph_updated": True,
        "processing_time_ms": 5000,
        "validation_results": [],
    }

    result = finalize_node(state)

    assert result["status"] == "completed"
    assert result["final_report"]["document_id"] == "test-123"
    assert result["final_report"]["invoice_number"] == "INV-001"
    assert result["final_report"]["graph_updated"] is True


def test_error_handler_node():
    """Test error handler generates failure report."""
    state = {
        "document_id": "test-123",
        "error_history": [
            {"node": "extract_text", "error": "Failed to read PDF"}
        ],
    }

    result = error_handler_node(state)

    assert result["status"] == "failed"
    assert result["final_report"]["status"] == "failed"
    assert len(result["final_report"]["errors"]) == 1
