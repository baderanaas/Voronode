"""LangGraph StateGraph definition for invoice processing workflow."""

import os
from typing import Optional
from backend.core.logging import get_logger

import psycopg
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from backend.core.state import WorkflowState
from backend.ingestion.pipeline.nodes import (
    extract_text_node,
    structure_invoice_node,
    validate_invoice_node,
    compliance_audit_node,
    critic_agent_node,
    quarantine_node,
    insert_graph_node,
    embed_vector_node,
    finalize_node,
    error_handler_node,
)
from backend.ingestion.pipeline.routing import (
    check_for_critical_failure,
    should_retry_extraction,
    route_by_validation_severity,
    route_by_compliance_severity,
    should_continue_after_graph,
)
from backend.core.config import settings

logger = get_logger(__name__)


def create_invoice_workflow_graph() -> StateGraph:
    """
    Create the LangGraph StateGraph for invoice processing.

    Workflow (Phase 4 with Compliance Auditor):
    1. extract_text → structure_invoice
    2. structure_invoice → [validate | retry (critic) | quarantine]
    3. critic → structure_invoice (retry loop)
    4. validate → [compliance_audit | correctable (critic) | quarantine]
    5. compliance_audit → [insert_graph | quarantine]
    6. insert_graph → [embed | finalize]
    7. embed → finalize
    8. finalize → END
    9. quarantine → END
    10. error_handler → END

    Returns:
        Compiled StateGraph
    """
    logger.info("creating_invoice_workflow_graph")

    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("extract_text", extract_text_node)
    workflow.add_node("structure_invoice", structure_invoice_node)
    workflow.add_node("validate", validate_invoice_node)
    workflow.add_node("compliance_audit", compliance_audit_node)
    workflow.add_node("critic", critic_agent_node)
    workflow.add_node("quarantine", quarantine_node)
    workflow.add_node("insert_graph", insert_graph_node)
    workflow.add_node("embed", embed_vector_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_node("error_handler", error_handler_node)

    # Set entry point
    workflow.set_entry_point("extract_text")

    # Edge 1: extract_text → [structure_invoice | error_handler]
    workflow.add_conditional_edges(
        "extract_text",
        check_for_critical_failure,
        {"continue": "structure_invoice", "error": "error_handler"},
    )

    # Edge 2: structure_invoice → [validate | retry (critic) | quarantine]
    workflow.add_conditional_edges(
        "structure_invoice",
        should_retry_extraction,
        {"validate": "validate", "retry": "critic", "quarantine": "quarantine"},
    )

    # Edge 3: critic → structure_invoice (retry loop)
    workflow.add_edge("critic", "structure_invoice")

    # Edge 4: validate → [compliance_audit (clean) | critic (correctable) | quarantine]
    workflow.add_conditional_edges(
        "validate",
        route_by_validation_severity,
        {"clean": "compliance_audit", "correctable": "critic", "quarantine": "quarantine"},
    )

    # Edge 4.5: compliance_audit → [insert_graph (clean) | quarantine (violations)]
    workflow.add_conditional_edges(
        "compliance_audit",
        route_by_compliance_severity,
        {"clean": "insert_graph", "quarantine": "quarantine"},
    )

    # Edge 5: insert_graph → [embed | finalize]
    workflow.add_conditional_edges(
        "insert_graph",
        should_continue_after_graph,
        {"embed": "embed", "finalize": "finalize"},
    )

    # Edge 6: embed → finalize
    workflow.add_edge("embed", "finalize")

    # Terminal edges
    workflow.add_edge("finalize", END)
    workflow.add_edge("quarantine", END)
    workflow.add_edge("error_handler", END)

    logger.info("invoice_workflow_graph_created")

    return workflow


def compile_workflow_with_checkpoints() -> StateGraph:
    """
    Compile the workflow with Postgres checkpoint persistence.

    Returns:
        Compiled workflow with checkpointing enabled
    """
    logger.info("compiling_workflow_with_checkpoints")

    workflow = create_invoice_workflow_graph()

    # Create checkpoint saver backed by Postgres
    conn = psycopg.connect(settings.database_url)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()  # idempotent — creates LangGraph tables on first run

    # Compile workflow
    compiled_workflow = workflow.compile(checkpointer=checkpointer)

    logger.info("workflow_compiled_successfully")

    return compiled_workflow


def get_workflow_visualization() -> str:
    """
    Generate a Mermaid diagram of the workflow graph.

    Returns:
        Mermaid diagram as string
    """
    workflow = create_invoice_workflow_graph()

    try:
        # LangGraph provides a draw_mermaid method
        mermaid_diagram = workflow.get_graph().draw_mermaid()
        return mermaid_diagram
    except Exception as e:
        logger.warning("workflow_visualization_failed", error=str(e))
        return "Visualization unavailable"
