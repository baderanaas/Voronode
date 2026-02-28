"""Conditional routing logic for LangGraph workflow."""

from typing import Literal
from backend.core.logging import get_logger

from backend.core.state import WorkflowState
from backend.core.config import settings

logger = get_logger(__name__)


def check_for_critical_failure(
    state: WorkflowState,
) -> Literal["continue", "error"]:
    """
    Check if text extraction succeeded.

    Args:
        state: Current workflow state

    Returns:
        "continue" if successful, "error" if critical failure
    """
    if state.get("status") == "failed":
        logger.debug(
            "routing_critical_failure",
            document_id=state["document_id"],
            route="error",
        )
        return "error"

    logger.debug(
        "routing_extraction_success",
        document_id=state["document_id"],
        route="continue",
    )
    return "continue"


def should_retry_extraction(
    state: WorkflowState,
) -> Literal["validate", "retry", "quarantine"]:
    """
    Route after structure_invoice_node based on extraction success.

    Logic:
    - If extracted_data exists and looks complete → "validate"
    - If extraction failed but retry_count < max_retries → "retry" (via critic)
    - Otherwise → "quarantine"

    Args:
        state: Current workflow state

    Returns:
        Routing decision
    """
    extracted_data = state.get("extracted_data")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    # Check if extraction succeeded
    if extracted_data and extracted_data.get("invoice_number"):
        logger.debug(
            "routing_extraction_valid",
            document_id=state["document_id"],
            route="validate",
        )
        return "validate"

    # Check retry budget
    if retry_count < max_retries:
        logger.debug(
            "routing_extraction_retry",
            document_id=state["document_id"],
            retry_count=retry_count,
            route="retry",
        )
        return "retry"

    # Max retries exceeded
    logger.warning(
        "routing_extraction_quarantine",
        document_id=state["document_id"],
        retry_count=retry_count,
        route="quarantine",
    )
    return "quarantine"


def route_by_validation_severity(
    state: WorkflowState,
) -> Literal["clean", "correctable", "quarantine"]:
    """
    Route after validate_invoice_node based on risk level.

    Logic:
    - risk_level == "low" → "clean" (proceed to graph insertion)
    - risk_level == "medium" AND retry_count < max → "correctable" (critic retry)
    - risk_level in ["high", "critical"] → "quarantine" (human review)
    - retry_count >= max_retries → "quarantine" (retries exhausted)

    Args:
        state: Current workflow state

    Returns:
        Routing decision
    """
    risk_level = state.get("risk_level", "unknown")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    # Low risk - proceed
    if risk_level == "low":
        logger.debug(
            "routing_validation_clean",
            document_id=state["document_id"],
            risk_level=risk_level,
            route="clean",
        )
        return "clean"

    # Medium risk - try correction if retries available
    if risk_level == "medium" and retry_count < max_retries:
        logger.debug(
            "routing_validation_correctable",
            document_id=state["document_id"],
            risk_level=risk_level,
            retry_count=retry_count,
            route="correctable",
        )
        return "correctable"

    # High/critical risk or retries exhausted - quarantine
    logger.warning(
        "routing_validation_quarantine",
        document_id=state["document_id"],
        risk_level=risk_level,
        retry_count=retry_count,
        route="quarantine",
    )
    return "quarantine"


def route_by_compliance_severity(
    state: WorkflowState,
) -> Literal["clean", "quarantine"]:
    """
    Route after compliance_audit_node based on compliance violations.

    Logic:
    - No compliance anomalies → "clean" (proceed to graph insertion)
    - Has critical compliance violations → "quarantine" (human review)
    - Has high severity violations above threshold → "quarantine"
    - Otherwise → "clean" (proceed with warnings)

    Args:
        state: Current workflow state

    Returns:
        Routing decision
    """
    if not settings.enable_compliance_audit:
        # If compliance auditing is disabled, always proceed
        return "clean"

    compliance_anomalies = state.get("compliance_anomalies", [])

    if not compliance_anomalies:
        logger.debug(
            "routing_compliance_clean",
            document_id=state["document_id"],
            route="clean",
        )
        return "clean"

    # Count by severity
    critical_count = sum(1 for a in compliance_anomalies if a.get("severity") == "critical")
    high_count = sum(1 for a in compliance_anomalies if a.get("severity") == "high")

    # Quarantine if above thresholds
    if critical_count >= settings.compliance_critical_threshold:
        logger.warning(
            "routing_compliance_quarantine_critical",
            document_id=state["document_id"],
            critical_count=critical_count,
            route="quarantine",
        )
        return "quarantine"

    if high_count >= settings.compliance_high_threshold:
        logger.warning(
            "routing_compliance_quarantine_high",
            document_id=state["document_id"],
            high_count=high_count,
            route="quarantine",
        )
        return "quarantine"

    # Below threshold - proceed with warnings
    logger.debug(
        "routing_compliance_clean_with_warnings",
        document_id=state["document_id"],
        anomalies_count=len(compliance_anomalies),
        route="clean",
    )
    return "clean"


def should_continue_after_graph(
    state: WorkflowState,
) -> Literal["embed", "finalize"]:
    """
    Route after insert_graph_node.

    Logic:
    - If graph_updated == True → "embed" (proceed to ChromaDB)
    - Otherwise → "finalize" (graceful degradation, skip embedding)

    Args:
        state: Current workflow state

    Returns:
        Routing decision
    """
    graph_updated = state.get("graph_updated", False)

    if graph_updated:
        logger.debug(
            "routing_graph_success",
            document_id=state["document_id"],
            route="embed",
        )
        return "embed"

    logger.warning(
        "routing_graph_failed",
        document_id=state["document_id"],
        route="finalize",
    )
    return "finalize"
