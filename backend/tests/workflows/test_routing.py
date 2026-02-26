"""Unit tests for workflow routing logic."""

import pytest

from backend.ingestion.pipeline.routing import (
    check_for_critical_failure,
    should_retry_extraction,
    route_by_validation_severity,
    should_continue_after_graph,
)


def test_check_for_critical_failure_success():
    """Test routing continues when no failure."""
    state = {"document_id": "test-123", "status": "processing"}

    result = check_for_critical_failure(state)

    assert result == "continue"


def test_check_for_critical_failure_error():
    """Test routing to error handler on failure."""
    state = {"document_id": "test-123", "status": "failed"}

    result = check_for_critical_failure(state)

    assert result == "error"


def test_should_retry_extraction_success():
    """Test routing to validate when extraction succeeds."""
    state = {
        "document_id": "test-123",
        "extracted_data": {"invoice_number": "INV-001"},
        "retry_count": 0,
        "max_retries": 3,
    }

    result = should_retry_extraction(state)

    assert result == "validate"


def test_should_retry_extraction_retry():
    """Test routing to critic for retry."""
    state = {
        "document_id": "test-123",
        "extracted_data": None,
        "retry_count": 1,
        "max_retries": 3,
    }

    result = should_retry_extraction(state)

    assert result == "retry"


def test_should_retry_extraction_quarantine():
    """Test routing to quarantine when retries exhausted."""
    state = {
        "document_id": "test-123",
        "extracted_data": None,
        "retry_count": 3,
        "max_retries": 3,
    }

    result = should_retry_extraction(state)

    assert result == "quarantine"


def test_route_by_validation_severity_clean():
    """Test routing to graph insertion for low risk."""
    state = {
        "document_id": "test-123",
        "risk_level": "low",
        "retry_count": 0,
        "max_retries": 3,
    }

    result = route_by_validation_severity(state)

    assert result == "clean"


def test_route_by_validation_severity_correctable():
    """Test routing to critic for medium risk with retries available."""
    state = {
        "document_id": "test-123",
        "risk_level": "medium",
        "retry_count": 1,
        "max_retries": 3,
    }

    result = route_by_validation_severity(state)

    assert result == "correctable"


def test_route_by_validation_severity_quarantine_high_risk():
    """Test routing to quarantine for high risk."""
    state = {
        "document_id": "test-123",
        "risk_level": "high",
        "retry_count": 0,
        "max_retries": 3,
    }

    result = route_by_validation_severity(state)

    assert result == "quarantine"


def test_route_by_validation_severity_quarantine_critical():
    """Test routing to quarantine for critical risk."""
    state = {
        "document_id": "test-123",
        "risk_level": "critical",
        "retry_count": 0,
        "max_retries": 3,
    }

    result = route_by_validation_severity(state)

    assert result == "quarantine"


def test_route_by_validation_severity_retries_exhausted():
    """Test routing to quarantine when retries exhausted."""
    state = {
        "document_id": "test-123",
        "risk_level": "medium",
        "retry_count": 3,
        "max_retries": 3,
    }

    result = route_by_validation_severity(state)

    assert result == "quarantine"


def test_should_continue_after_graph_success():
    """Test routing to embed when graph insertion succeeds."""
    state = {
        "document_id": "test-123",
        "graph_updated": True,
    }

    result = should_continue_after_graph(state)

    assert result == "embed"


def test_should_continue_after_graph_failure():
    """Test routing to finalize when graph insertion fails."""
    state = {
        "document_id": "test-123",
        "graph_updated": False,
    }

    result = should_continue_after_graph(state)

    assert result == "finalize"
