"""LangGraph node functions for invoice processing workflow."""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import structlog

from backend.core.state import WorkflowState
from backend.core.models import Invoice, LineItem
from backend.agents.extractor import InvoiceExtractor
from backend.agents.validator import InvoiceValidator
from backend.services.graph_builder import GraphBuilder
from backend.services.llm_client import GroqClient
from backend.vector.client import ChromaDBClient

logger = structlog.get_logger()


def extract_text_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 1: Extract raw text from PDF using pdfplumber.

    Args:
        state: Current workflow state

    Returns:
        Updated state with raw_text or error
    """
    logger.info("node_extract_text_started", document_id=state["document_id"])

    try:
        extractor = InvoiceExtractor()
        raw_text = extractor.extract_text_from_pdf(Path(state["document_path"]))

        logger.info(
            "node_extract_text_success",
            document_id=state["document_id"],
            text_length=len(raw_text),
        )

        return {
            "raw_text": raw_text,
            "status": "processing",
        }

    except Exception as e:
        error = {
            "node": "extract_text",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(
            "node_extract_text_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {
            "error_history": [error],
            "status": "failed",
        }


def structure_invoice_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 2: Convert raw text to structured Invoice using Groq LLM.

    Supports retry with critic feedback.

    Args:
        state: Current workflow state with raw_text

    Returns:
        Updated state with extracted_data or retry feedback
    """
    logger.info(
        "node_structure_invoice_started",
        document_id=state["document_id"],
        retry_count=state.get("retry_count", 0),
    )

    try:
        extractor = InvoiceExtractor()

        # If this is a retry, incorporate critic feedback
        raw_text = state["raw_text"]
        if state.get("critic_feedback"):
            raw_text = f"{raw_text}\n\nCRITIC FEEDBACK (FIX THESE ISSUES):\n{state['critic_feedback']}"

        invoice_data = extractor.structure_invoice(raw_text)

        # Calculate confidence based on completeness
        confidence = _calculate_extraction_confidence(invoice_data)

        logger.info(
            "node_structure_invoice_success",
            document_id=state["document_id"],
            invoice_number=invoice_data.get("invoice_number"),
            confidence=confidence,
        )

        return {
            "extracted_data": invoice_data,
            "extraction_confidence": confidence,
            "status": "processing",
        }

    except Exception as e:
        error = {
            "node": "structure_invoice",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "retry_count": state.get("retry_count", 0),
        }

        logger.error(
            "node_structure_invoice_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {
            "error_history": [error],
        }


def validate_invoice_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 3: Run comprehensive validation on extracted invoice.

    Args:
        state: Current workflow state with extracted_data

    Returns:
        Updated state with anomalies and risk_level
    """
    logger.info(
        "node_validate_invoice_started",
        document_id=state["document_id"],
    )

    try:
        # Convert extracted_data to Invoice model
        invoice = _dict_to_invoice(state["extracted_data"])

        validator = InvoiceValidator()
        anomalies = validator.validate_invoice(invoice)

        # Calculate risk level based on anomaly severity
        risk_level = _calculate_risk_level(anomalies)

        # Convert anomalies to dicts
        anomaly_dicts = [anomaly.to_dict() for anomaly in anomalies]

        logger.info(
            "node_validate_invoice_success",
            document_id=state["document_id"],
            anomalies_count=len(anomalies),
            risk_level=risk_level,
        )

        return {
            "anomalies": anomaly_dicts,
            "risk_level": risk_level,
            "validation_results": [{
                "timestamp": datetime.now().isoformat(),
                "anomalies_count": len(anomalies),
                "risk_level": risk_level,
            }],
            "status": "processing",
        }

    except Exception as e:
        error = {
            "node": "validate_invoice",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(
            "node_validate_invoice_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {
            "error_history": [error],
            "status": "failed",
        }


def critic_agent_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 4: Analyze anomalies and provide correction feedback.

    Args:
        state: Current workflow state with anomalies

    Returns:
        Updated state with critic_feedback and incremented retry_count
    """
    logger.info(
        "node_critic_agent_started",
        document_id=state["document_id"],
        anomalies_count=len(state.get("anomalies", [])),
    )

    try:
        llm_client = GroqClient()

        # Build critique prompt
        anomalies_text = "\n".join([
            f"- {a['type']}: {a['message']}"
            for a in state.get("anomalies", [])
        ])

        prompt = f"""You are a financial document quality control expert. Review the following extraction anomalies and provide SPECIFIC corrections.

EXTRACTED INVOICE DATA:
{state.get("extracted_data", {})}

ANOMALIES DETECTED:
{anomalies_text}

Provide specific instructions on how to fix these issues. Focus on:
1. Math errors (recalculate totals)
2. Missing or incorrect fields
3. Date logic issues
4. Cost code corrections

Return ONLY the correction instructions, be concise and actionable.
"""

        feedback = llm_client.extract_json(prompt=prompt)

        # Extract feedback text from response
        if isinstance(feedback, dict):
            feedback_text = feedback.get("corrections", str(feedback))
        else:
            feedback_text = str(feedback)

        retry_count = state.get("retry_count", 0) + 1

        logger.info(
            "node_critic_agent_success",
            document_id=state["document_id"],
            retry_count=retry_count,
        )

        return {
            "critic_feedback": feedback_text,
            "retry_count": retry_count,
            "status": "processing",
        }

    except Exception as e:
        error = {
            "node": "critic_agent",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(
            "node_critic_agent_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {
            "error_history": [error],
        }


def quarantine_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 5: Pause workflow for human review.

    Args:
        state: Current workflow state

    Returns:
        Updated state with paused=True
    """
    logger.info(
        "node_quarantine_started",
        document_id=state["document_id"],
        risk_level=state.get("risk_level"),
    )

    # Determine pause reason
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    risk_level = state.get("risk_level", "unknown")

    if retry_count >= max_retries:
        pause_reason = f"Max retries ({max_retries}) exceeded"
    elif risk_level in ["high", "critical"]:
        pause_reason = f"High risk level: {risk_level}"
    else:
        pause_reason = "Manual review required"

    logger.info(
        "node_quarantine_complete",
        document_id=state["document_id"],
        pause_reason=pause_reason,
    )

    return {
        "paused": True,
        "pause_reason": pause_reason,
        "status": "quarantined",
    }


def insert_graph_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 6: Insert invoice into Neo4j knowledge graph.

    Args:
        state: Current workflow state with extracted_data

    Returns:
        Updated state with graph_updated=True and neo4j_id
    """
    logger.info(
        "node_insert_graph_started",
        document_id=state["document_id"],
    )

    try:
        # Convert extracted_data to Invoice model
        invoice = _dict_to_invoice(state["extracted_data"])

        graph_builder = GraphBuilder()
        invoice_id = graph_builder.insert_invoice(invoice)

        logger.info(
            "node_insert_graph_success",
            document_id=state["document_id"],
            neo4j_id=invoice_id,
        )

        return {
            "graph_updated": True,
            "neo4j_id": invoice_id,
            "status": "processing",
        }

    except Exception as e:
        error = {
            "node": "insert_graph",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(
            "node_insert_graph_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {
            "error_history": [error],
            "graph_updated": False,
        }


def embed_vector_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 7: Embed invoice in ChromaDB vector store.

    Non-blocking: Failures logged but don't abort workflow.

    Args:
        state: Current workflow state with extracted_data

    Returns:
        Updated state (no critical changes)
    """
    logger.info(
        "node_embed_vector_started",
        document_id=state["document_id"],
    )

    try:
        invoice_data = state["extracted_data"]
        chroma_client = ChromaDBClient()

        # Create searchable text
        invoice_text = f"""
        Invoice: {invoice_data.get('invoice_number')}
        Date: {invoice_data.get('date')}
        Contractor: {invoice_data.get('contractor_name', 'Unknown')}
        Amount: ${invoice_data.get('total_amount')}

        Line Items:
        """

        for item in invoice_data.get("line_items", []):
            invoice_text += f"\n- {item.get('cost_code')}: {item.get('description')} (${item.get('total')})"

        chroma_client.add_document(
            collection_name="invoices",
            doc_id=state.get("neo4j_id", state["document_id"]),
            text=invoice_text,
            metadata={
                "invoice_number": invoice_data.get("invoice_number"),
                "date": str(invoice_data.get("date")),
                "amount": float(invoice_data.get("total_amount", 0)),
                "contractor_name": invoice_data.get("contractor_name", "Unknown"),
            },
        )

        logger.info(
            "node_embed_vector_success",
            document_id=state["document_id"],
        )

        return {"status": "processing"}

    except Exception as e:
        # Non-blocking failure
        logger.warning(
            "node_embed_vector_failed",
            document_id=state["document_id"],
            error=str(e),
        )

        return {}  # Don't update state on failure


def finalize_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 8: Generate final report and mark workflow complete.

    Args:
        state: Current workflow state

    Returns:
        Updated state with final_report and status=completed
    """
    logger.info(
        "node_finalize_started",
        document_id=state["document_id"],
    )

    final_report = {
        "document_id": state["document_id"],
        "invoice_number": state.get("extracted_data", {}).get("invoice_number"),
        "neo4j_id": state.get("neo4j_id"),
        "extraction_confidence": state.get("extraction_confidence"),
        "risk_level": state.get("risk_level"),
        "anomalies_count": len(state.get("anomalies", [])),
        "retry_count": state.get("retry_count", 0),
        "graph_updated": state.get("graph_updated", False),
        "processing_time_ms": state.get("processing_time_ms", 0),
        "validation_summary": state.get("validation_results", []),
    }

    logger.info(
        "node_finalize_complete",
        document_id=state["document_id"],
        final_report=final_report,
    )

    return {
        "final_report": final_report,
        "status": "completed",
    }


def error_handler_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Node 9: Handle terminal failures.

    Args:
        state: Current workflow state with error_history

    Returns:
        Updated state with final_report and status=failed
    """
    logger.error(
        "node_error_handler_started",
        document_id=state["document_id"],
        errors_count=len(state.get("error_history", [])),
    )

    final_report = {
        "document_id": state["document_id"],
        "status": "failed",
        "errors": state.get("error_history", []),
        "last_successful_node": _get_last_successful_node(state),
    }

    logger.error(
        "node_error_handler_complete",
        document_id=state["document_id"],
        final_report=final_report,
    )

    return {
        "final_report": final_report,
        "status": "failed",
    }


# Helper functions

def _calculate_extraction_confidence(invoice_data: Dict[str, Any]) -> float:
    """Calculate confidence score based on data completeness."""
    required_fields = ["invoice_number", "date", "contractor_name", "total_amount", "line_items"]

    present_count = sum(1 for field in required_fields if invoice_data.get(field))
    confidence = present_count / len(required_fields)

    # Boost confidence if line items have cost codes
    if invoice_data.get("line_items"):
        items_with_codes = sum(
            1 for item in invoice_data["line_items"]
            if item.get("cost_code") and item["cost_code"] != "99-999"
        )
        code_ratio = items_with_codes / len(invoice_data["line_items"])
        confidence = (confidence + code_ratio) / 2

    return round(confidence, 2)


def _calculate_risk_level(anomalies) -> str:
    """Calculate risk level based on anomaly severities."""
    if not anomalies:
        return "low"

    severity_counts = {
        "high": sum(1 for a in anomalies if a.severity == "high"),
        "medium": sum(1 for a in anomalies if a.severity == "medium"),
        "low": sum(1 for a in anomalies if a.severity == "low"),
    }

    if severity_counts["high"] >= 2:
        return "critical"
    elif severity_counts["high"] >= 1:
        return "high"
    elif severity_counts["medium"] >= 3:
        return "high"
    elif severity_counts["medium"] >= 1:
        return "medium"
    else:
        return "low"


def _dict_to_invoice(invoice_data: Dict[str, Any]) -> Invoice:
    """Convert extracted dictionary to Invoice model."""
    line_items = []
    for item_data in invoice_data.get("line_items", []):
        line_item = LineItem(**item_data)
        line_items.append(line_item)

    invoice = Invoice(
        invoice_number=invoice_data["invoice_number"],
        date=invoice_data["date"],
        due_date=invoice_data.get("due_date"),
        contractor_id=invoice_data.get("contractor_name", "Unknown"),
        contract_id=invoice_data.get("contract_id"),
        amount=invoice_data["total_amount"],
        line_items=line_items,
        extracted_at=datetime.now(),
        extraction_confidence=invoice_data.get("extraction_confidence", 0.9),
    )

    return invoice


def _get_last_successful_node(state: WorkflowState) -> str:
    """Determine the last successfully completed node."""
    if state.get("graph_updated"):
        return "insert_graph"
    elif state.get("anomalies") is not None:
        return "validate_invoice"
    elif state.get("extracted_data"):
        return "structure_invoice"
    elif state.get("raw_text"):
        return "extract_text"
    else:
        return "none"
