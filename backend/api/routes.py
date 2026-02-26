"""API routes for invoice processing."""

import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
import structlog
import json

from backend.agents.orchestrator import create_multi_agent_graph
from backend.agents.orchestrator import create_multi_agent_graph


from backend.api.schemas import (
    InvoiceUploadResponse,
    HealthResponse,
    ValidationAnomalyResponse,
    WorkflowStatusResponse,
    QuarantinedWorkflowResponse,
    WorkflowResumeRequest,
    BudgetDetailResponse,
    BudgetVarianceResponse,
    BudgetLineResponse,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
)
from backend.services.graph_builder import GraphBuilder
from backend.services.workflow_manager import WorkflowManager
from backend.vector.client import ChromaDBClient
from backend.graph.client import Neo4jClient
from backend.core.config import settings

logger = structlog.get_logger()

router = APIRouter()

# Initialize services (lazy loading in production would be better)
graph_builder = GraphBuilder()
chroma_client = ChromaDBClient()
workflow_manager = WorkflowManager()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check service connectivity.

    Returns:
        Status of Neo4j and ChromaDB connections
    """
    neo4j_client = Neo4jClient()

    services_status = {
        "neo4j": neo4j_client.verify_connectivity(),
        "chromadb": chroma_client.verify_connectivity(),
    }

    overall_status = "healthy" if all(services_status.values()) else "degraded"

    logger.info("health_check", status=overall_status, services=services_status)

    return HealthResponse(
        status=overall_status, services=services_status, timestamp=datetime.now(timezone.utc)
    )


# Phase 3: LangGraph Workflow Endpoints


@router.get("/workflows/quarantined", response_model=List[QuarantinedWorkflowResponse])
async def get_quarantined_workflows():
    """
    Get all workflows awaiting human review.

    Returns:
        List of quarantined workflows
    """
    logger.info("quarantined_workflows_requested")

    try:
        workflows = workflow_manager.get_quarantined_workflows()

        responses = []
        for wf in workflows:
            state = wf["state"]
            anomaly_dicts = state.get("anomalies", [])

            responses.append(
                QuarantinedWorkflowResponse(
                    document_id=wf["document_id"],
                    status=wf["status"],
                    risk_level=wf["risk_level"],
                    retry_count=wf["retry_count"],
                    pause_reason=state.get("pause_reason"),
                    anomalies=[ValidationAnomalyResponse(**a) for a in anomaly_dicts],
                    created_at=wf["created_at"],
                    updated_at=wf["updated_at"],
                )
            )

        logger.info("quarantined_workflows_retrieved", count=len(responses))

        return responses

    except Exception as e:
        logger.error("quarantined_workflows_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve quarantined workflows: {e}"
        )


@router.post("/workflows/{document_id}/resume", response_model=InvoiceUploadResponse)
async def resume_workflow(document_id: str, request: WorkflowResumeRequest):
    """
    Resume a quarantined workflow with human feedback.

    Args:
        document_id: Workflow document ID
        request: Human feedback (approved/corrections)

    Returns:
        Final processing result
    """
    logger.info(
        "workflow_resume_requested",
        document_id=document_id,
        approved=request.approved,
    )

    try:
        # Build feedback dictionary
        human_feedback = {
            "approved": request.approved,
            "corrections": request.corrections or {},
            "notes": request.notes,
        }

        # Resume workflow
        final_state = workflow_manager.resume_workflow(document_id, human_feedback)

        # Extract response data
        extracted_data = final_state.get("extracted_data", {})
        anomaly_dicts = final_state.get("anomalies", [])

        anomaly_responses = [ValidationAnomalyResponse(**a) for a in anomaly_dicts]

        return InvoiceUploadResponse(
            success=final_state.get("status") == "completed",
            message=f"Workflow resumed: {final_state.get('status')}",
            invoice_id=final_state.get("neo4j_id"),
            invoice_number=extracted_data.get("invoice_number"),
            amount=extracted_data.get("total_amount"),
            line_items_count=len(extracted_data.get("line_items", [])),
            validation_anomalies=anomaly_responses,
            processing_time_seconds=final_state.get("processing_time_ms", 0) / 1000.0,
            workflow_id=document_id,
            retry_count=final_state.get("retry_count", 0),
            risk_level=final_state.get("risk_level"),
            requires_review=False,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("workflow_resume_failed", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {e}")


@router.get("/workflows/{document_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(document_id: str):
    """
    Get current workflow status.

    Args:
        document_id: Workflow document ID

    Returns:
        Workflow status
    """
    logger.info("workflow_status_requested", document_id=document_id)

    try:
        workflow = workflow_manager.get_workflow_status(document_id)

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return WorkflowStatusResponse(
            document_id=workflow["document_id"],
            status=workflow["status"],
            paused=workflow["paused"],
            risk_level=workflow["risk_level"],
            retry_count=workflow["retry_count"],
            created_at=workflow["created_at"],
            updated_at=workflow["updated_at"],
            state=workflow["state"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("workflow_status_failed", document_id=document_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get workflow status: {e}"
        )


@router.get("/workflows")
async def list_workflows(status: str = None, limit: int = 100):
    """
    List all workflows, optionally filtered by status.

    Args:
        status: Optional status filter (completed, quarantined, processing, failed)
        limit: Maximum number of workflows to return

    Returns:
        List of workflows
    """
    logger.info("workflows_list_requested", status=status, limit=limit)

    try:
        workflows = workflow_manager.list_workflows(status=status, limit=limit)
        return workflows

    except Exception as e:
        logger.error("workflows_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list workflows: {e}")


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """
    Get detailed workflow information by ID.

    Args:
        workflow_id: Workflow ID (document_id)

    Returns:
        Complete workflow state and metadata
    """
    logger.info("workflow_get_requested", workflow_id=workflow_id)

    try:
        workflow = workflow_manager.get_workflow_status(workflow_id)

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return workflow

    except HTTPException:
        raise
    except Exception as e:
        logger.error("workflow_get_failed", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get workflow: {e}")


@router.get("/graph/stats")
async def get_graph_stats():
    """
    Get Neo4j graph database statistics.

    Returns:
        Node counts, relationship counts, and other graph metrics
    """
    logger.info("graph_stats_requested")

    try:
        neo4j_client = Neo4jClient()

        # Count nodes by label
        node_counts_query = """
        MATCH (n)
        RETURN labels(n)[0] as label, count(*) as count
        """
        node_results = neo4j_client.run_query(node_counts_query)

        # Count relationships
        rel_count_query = """
        MATCH ()-[r]->()
        RETURN count(r) as count
        """
        rel_results = neo4j_client.run_query(rel_count_query)

        # Build response
        stats = {
            "total_nodes": sum(r["count"] for r in node_results),
            "total_relationships": rel_results[0]["count"] if rel_results else 0,
        }

        # Add individual node type counts
        for result in node_results:
            label = result["label"]
            count = result["count"]
            stats[f"{label.lower()}_count"] = count

        logger.info("graph_stats_retrieved", stats=stats)
        return stats

    except Exception as e:
        logger.error("graph_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get graph stats: {e}")


@router.get("/budgets/{budget_id}", response_model=BudgetDetailResponse)
async def get_budget(budget_id: str):
    """
    Get budget details by ID.

    Args:
        budget_id: Budget ID

    Returns:
        Budget details with all budget lines
    """
    logger.info("budget_detail_requested", budget_id=budget_id)

    try:
        budget_data = graph_builder.get_budget_by_id(budget_id)

        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")

        # Convert budget lines to response format
        from backend.api.schemas import BudgetLineResponse

        budget_lines = [
            BudgetLineResponse(
                id=line["id"],
                cost_code=line["cost_code"],
                description=line["description"],
                allocated=line["allocated"],
                spent=line["spent"],
                remaining=line["remaining"],
                variance_percent=(
                    ((line["spent"] - line["allocated"]) / line["allocated"] * 100)
                    if line["allocated"] > 0
                    else 0
                ),
            )
            for line in budget_data["budget_lines"]
        ]

        return BudgetDetailResponse(
            id=budget_data["id"],
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            total_allocated=budget_data["total_allocated"],
            total_spent=budget_data["total_spent"],
            total_remaining=budget_data["total_remaining"],
            line_count=budget_data["line_count"],
            status=budget_data["status"],
            budget_lines=budget_lines,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_detail_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budget: {e}")


@router.get("/budgets/project/{project_id}")
async def get_project_budgets(project_id: str):
    """
    Get all budgets for a project.

    Args:
        project_id: Project ID

    Returns:
        List of budgets for the project
    """
    logger.info("project_budgets_requested", project_id=project_id)

    try:
        budgets = graph_builder.get_budgets_by_project(project_id)

        return {
            "project_id": project_id,
            "budget_count": len(budgets),
            "budgets": budgets,
        }

    except Exception as e:
        logger.error("project_budgets_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budgets: {e}")


@router.get("/budgets/{budget_id}/variance", response_model=BudgetVarianceResponse)
async def get_budget_variance(budget_id: str):
    """
    Calculate budget variance (budget vs actual spend).

    Args:
        budget_id: Budget ID

    Returns:
        Variance analysis with per-line breakdown
    """
    logger.info("budget_variance_requested", budget_id=budget_id)

    try:
        budget_data = graph_builder.get_budget_by_id(budget_id)

        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")

        # Calculate overall variance
        total_allocated = budget_data["total_allocated"]
        total_spent = budget_data["total_spent"]
        overall_variance = (
            ((total_spent - total_allocated) / total_allocated * 100)
            if total_allocated > 0
            else 0
        )
        overall_variance_amount = total_spent - total_allocated

        # Calculate per-line variance
        line_variances = []
        overrun_lines = []
        underrun_lines = []
        at_risk_lines = []

        for line in budget_data["budget_lines"]:
            allocated = line["allocated"]
            spent = line["spent"]
            variance_pct = (
                ((spent - allocated) / allocated * 100) if allocated > 0 else 0
            )
            variance_amt = spent - allocated
            utilization_pct = (spent / allocated * 100) if allocated > 0 else 0

            line_variances.append(
                {
                    "cost_code": line["cost_code"],
                    "description": line["description"],
                    "allocated": allocated,
                    "spent": spent,
                    "variance_percent": round(variance_pct, 2),
                    "variance_amount": round(variance_amt, 2),
                    "utilization_percent": round(utilization_pct, 2),
                }
            )

            # Categorize lines
            if variance_amt > 0:
                overrun_lines.append(line["cost_code"])
            elif variance_amt < 0:
                underrun_lines.append(line["cost_code"])

            if utilization_pct > 90:
                at_risk_lines.append(line["cost_code"])

        return BudgetVarianceResponse(
            budget_id=budget_id,
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            overall_variance=round(overall_variance, 2),
            overall_variance_amount=round(overall_variance_amount, 2),
            line_variances=line_variances,
            overrun_lines=overrun_lines,
            underrun_lines=underrun_lines,
            at_risk_lines=at_risk_lines,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_variance_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate variance: {e}"
        )


@router.post("/graph/query")
async def query_graph(query: dict):
    """
    Execute custom Cypher query on Neo4j.

    Args:
        query: Dictionary with 'query' key containing Cypher query string

    Returns:
        Query results as list of records
    """
    cypher_query = query.get("query")

    if not cypher_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body")

    logger.info("graph_query_requested", query=cypher_query[:100])

    try:
        neo4j_client = Neo4jClient()
        results = neo4j_client.run_query(cypher_query)

        logger.info("graph_query_executed", record_count=len(results))
        return {"records": results, "count": len(results)}

    except Exception as e:
        logger.error("graph_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")


# Phase 7: Conversational AI Chat Endpoint


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Conversational AI endpoint using multi-agent system.

    Pipeline:
    1. Planner analyzes query and routes (generic_response, execution_plan, clarification)
    2. If execution_plan, Executor runs tools in one_way or react mode
    3. Validator checks response quality (retry loop if needed)
    4. Responder formats response with markdown

    Args:
        request: User message and conversation history

    Returns:
        Formatted response with display format and data
    """
    start_time = time.time()

    logger.info("chat_request_received", message=request.message[:100])

    try:
        # Import orchestrator
        from backend.agents.orchestrator import create_multi_agent_graph

        # Initialize multi-agent graph
        graph = create_multi_agent_graph()

        # Convert conversation history to state format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.conversation_history
        ]

        # Create initial state
        initial_state = {
            "user_query": request.message,
            "conversation_history": history,
            "retry_count": 0,
            "current_step": 0,
            "completed_steps": [],
            "react_max_steps": 5,
        }

        # Execute graph
        config = {"configurable": {"thread_id": request.session_id or "default"}}
        final_state = graph.invoke(initial_state, config)

        # Extract response
        response_text = final_state.get("final_response", "")
        display_format = final_state.get("display_format", "text")
        display_data = final_state.get("display_data")
        route = final_state.get("route", "unknown")
        execution_mode = final_state.get("execution_mode")

        # Build metadata
        metadata = {
            "processing_time_seconds": round(time.time() - start_time, 2),
            "retry_count": final_state.get("retry_count", 0),
            "react_steps": len(final_state.get("completed_steps", [])),
        }

        logger.info(
            "chat_request_complete",
            route=route,
            execution_mode=execution_mode,
            processing_time=metadata["processing_time_seconds"],
        )

        return ChatResponse(
            response=response_text,
            display_format=display_format,
            display_data=display_data,
            route=route,
            execution_mode=execution_mode,
            metadata=metadata,
            session_id=request.session_id,
        )

    except Exception as e:
        logger.error("chat_request_failed", error=str(e), message=request.message[:100])

        # Return friendly error response
        return ChatResponse(
            response=f"I encountered an error while processing your request: {str(e)}",
            display_format="text",
            display_data=None,
            route="generic_response",
            execution_mode=None,
            metadata={
                "error": str(e),
                "processing_time_seconds": round(time.time() - start_time, 2),
            },
            session_id=request.session_id,
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming conversational AI endpoint using multi-agent system.

    Returns Server-Sent Events (SSE) with real-time updates as the multi-agent
    system processes the query.

    Events:
    - planner: Planning stage updates (route, execution mode, plan)
    - executor: Tool execution updates (tool name, status, results)
    - planner_react: ReAct planning updates (next step decision)
    - validator: Validation updates (validation result, issues)
    - responder: Final response formatting
    - complete: Processing complete with final response
    - error: Error occurred during processing

    Args:
        request: User message and conversation history

    Returns:
        StreamingResponse with Server-Sent Events
    """

    async def generate_events():
        """Generate SSE events from multi-agent graph stream."""
        start_time = time.time()

        logger.info("chat_stream_request_received", message=request.message[:100])

        try:
            # Initialize multi-agent graph
            graph = create_multi_agent_graph()

            # Convert conversation history to state format
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]

            # Create initial state
            initial_state = {
                "user_query": request.message,
                "conversation_history": history,
                "retry_count": 0,
                "current_step": 0,
                "completed_steps": [],
                "react_max_steps": 5,
            }

            # Execute graph with streaming
            config = {"configurable": {"thread_id": request.session_id or "default"}}

            # Stream state updates
            for chunk in graph.stream(initial_state, config):
                node_name = list(chunk.keys())[0]
                state_update = chunk[node_name]

                # Create event based on node
                event_data = _create_event_data(node_name, state_update)

                if event_data:
                    event = ChatStreamEvent(
                        event=node_name,
                        data=event_data,
                        timestamp=datetime.now(timezone.utc),
                    )

                    # Yield SSE format: data: {json}\n\n
                    yield f"data: {event.model_dump_json()}\n\n"

                    logger.debug(
                        "chat_stream_event_sent",
                        node=node_name,
                        session_id=request.session_id,
                    )

            # Send completion event
            processing_time = time.time() - start_time

            complete_event = ChatStreamEvent(
                event="complete",
                data={
                    "message": "Processing complete",
                    "processing_time_seconds": round(processing_time, 2),
                },
                timestamp=datetime.now(timezone.utc),
            )

            yield f"data: {complete_event.model_dump_json()}\n\n"

            logger.info(
                "chat_stream_complete",
                processing_time=processing_time,
                session_id=request.session_id,
            )

        except Exception as e:
            logger.error(
                "chat_stream_failed",
                error=str(e),
                message=request.message[:100],
            )

            # Send error event
            error_event = ChatStreamEvent(
                event="error",
                data={
                    "error": str(e),
                    "message": f"I encountered an error while processing your request: {str(e)}",
                },
                timestamp=datetime.now(timezone.utc),
            )

            yield f"data: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _create_event_data(
    node_name: str, state_update: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Create event data from state update based on node type.

    Args:
        node_name: Name of the node that executed (planner, executor, etc.)
        state_update: State updates from the node

    Returns:
        Event data dictionary or None if no relevant data
    """
    if node_name == "planner":
        planner_output = state_update.get("planner_output", {})
        return {
            "stage": "planning",
            "route": state_update.get("route"),
            "execution_mode": state_update.get("execution_mode"),
            "plan": planner_output.get("plan", {}),
            "response": planner_output.get("response", ""),
            "retry_count": state_update.get("retry_count", 0),
        }

    elif node_name == "executor":
        execution_results = state_update.get("execution_results", {})
        execution_mode = state_update.get("execution_mode", "one_way")

        if execution_mode == "one_way":
            # Return all results for one-way mode
            return {
                "stage": "execution",
                "mode": "one_way",
                "status": execution_results.get("status"),
                "results": execution_results.get("results", []),
                "metadata": execution_results.get("metadata", {}),
            }
        else:
            # Return single step result for react mode
            completed_steps = state_update.get("completed_steps", [])
            latest_step = completed_steps[-1] if completed_steps else {}

            # Determine status from latest step
            step_status = (
                latest_step.get("status", "unknown") if latest_step else "unknown"
            )

            return {
                "stage": "execution",
                "mode": "react",
                "status": step_status,
                "current_step": state_update.get("current_step", 0),
                "step_result": latest_step,
                "total_steps": len(completed_steps),
            }

    elif node_name == "planner_react":
        # Get the previous step's results to show what planner is analyzing
        completed_steps = state_update.get("completed_steps", [])
        previous_result = completed_steps[-1] if completed_steps else None

        return {
            "stage": "react_planning",
            "continue": state_update.get("react_continue", False),
            "next_step": state_update.get("next_step", {}),
            "current_step": state_update.get("current_step", 0),
            "previous_result": previous_result,  # Show what data planner received
        }

    elif node_name == "validator":
        validation_result = state_update.get("validation_result", {})
        return {
            "stage": "validation",
            "valid": validation_result.get("valid", False),
            "issues": validation_result.get("issues", []),
            "retry_suggestion": validation_result.get("retry_suggestion", ""),
        }

    elif node_name == "responder":
        return {
            "stage": "formatting",
            "response": state_update.get("final_response", ""),
            "display_format": state_update.get("display_format", "text"),
            "display_data": state_update.get("display_data"),
        }

    elif node_name == "upload_agent":
        execution_results = state_update.get("execution_results", {})
        return {
            "stage": "upload",
            "status": execution_results.get("status"),
            "results": execution_results.get("results", []),
            "metadata": execution_results.get("metadata", {}),
        }

    return None


@router.post("/chat/upload", response_model=ChatResponse)
async def chat_upload(
    files: List[UploadFile] = File(...),
    message: str = Form(""),
    session_id: str = Form(None),
):
    """
    Multi-file upload endpoint that routes through the multi-agent system.

    The planner classifies each file (invoice/contract/budget) and emits an
    upload_plan. The UploadAgent processes all files, then the Validator and
    Responder format the result.

    Args:
        files: One or more uploaded files (PDF, xlsx, csv)
        message: Optional user instruction
        session_id: Optional session ID for conversation persistence

    Returns:
        ChatResponse with processing summary
    """
    start_time = time.time()

    logger.info("chat_upload_request_received", file_count=len(files))

    temp_paths = []

    try:
        # Save each file to a named temp file
        file_descriptions = []
        for uploaded_file in files:
            suffix = Path(uploaded_file.filename).suffix or ".tmp"

            # Validate file size
            content = await uploaded_file.read()
            if len(content) > settings.api_upload_max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{uploaded_file.filename}' too large. "
                    f"Maximum size: {settings.api_upload_max_size} bytes",
                )

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            temp_paths.append(tmp_path)
            file_descriptions.append(f"- {uploaded_file.filename} → {tmp_path}")
            logger.info(
                "chat_upload_temp_saved", filename=uploaded_file.filename, path=tmp_path
            )

        # Build the initial message for the planner
        file_list_str = "\n".join(file_descriptions)
        count = len(files)
        initial_message = f"User uploaded {count} file(s):\n{file_list_str}\n"
        if message.strip():
            initial_message += f"\n{message.strip()}\n"
        initial_message += "\nPlease identify and process each document."

        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": initial_message,
            "conversation_history": [],
            "retry_count": 0,
            "current_step": 0,
            "completed_steps": [],
            "react_max_steps": 5,
        }

        config = {"configurable": {"thread_id": session_id or "upload_default"}}
        final_state = graph.invoke(initial_state, config)

        response_text = final_state.get("final_response", "")
        display_format = final_state.get("display_format", "text")
        display_data = final_state.get("display_data")
        route = final_state.get("route", "unknown")

        metadata = {
            "processing_time_seconds": round(time.time() - start_time, 2),
            "file_count": count,
            "retry_count": final_state.get("retry_count", 0),
        }

        logger.info(
            "chat_upload_complete",
            route=route,
            processing_time=metadata["processing_time_seconds"],
        )

        return ChatResponse(
            response=response_text,
            display_format=display_format,
            display_data=display_data,
            route=route,
            execution_mode="upload",
            metadata=metadata,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_upload_failed", error=str(e))
        return ChatResponse(
            response=f"I encountered an error while processing your files: {str(e)}",
            display_format="text",
            display_data=None,
            route="generic_response",
            execution_mode=None,
            metadata={
                "error": str(e),
                "processing_time_seconds": round(time.time() - start_time, 2),
            },
            session_id=session_id,
        )
    finally:
        # Clean up any temp files not already deleted by tools
        for tmp_path in temp_paths:
            try:
                p = Path(tmp_path)
                if p.exists():
                    p.unlink()
                    logger.debug("chat_upload_temp_cleaned", path=tmp_path)
            except Exception as cleanup_err:
                logger.warning(
                    "chat_upload_cleanup_failed", path=tmp_path, error=str(cleanup_err)
                )
