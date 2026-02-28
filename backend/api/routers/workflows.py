"""Workflow management endpoints."""

from typing import List, Optional

from backend.core.logging import get_logger
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import (
    InvoiceUploadResponse,
    QuarantinedWorkflowResponse,
    ValidationAnomalyResponse,
    WorkflowResumeRequest,
    WorkflowStatusResponse,
)
from backend.auth.dependencies import get_current_user
from backend.services.workflow_manager import WorkflowManager

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = get_logger(__name__)

_workflow_manager: WorkflowManager | None = None


def get_workflow_manager() -> WorkflowManager:
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager


@router.get("/quarantined", response_model=List[QuarantinedWorkflowResponse])
async def get_quarantined_workflows(current_user: dict = Depends(get_current_user)):
    """Get all workflows awaiting human review."""
    user_id = current_user["id"]
    logger.debug("quarantined_workflows_requested", user_id=user_id)
    try:
        workflows = get_workflow_manager().get_quarantined_workflows(user_id=user_id)
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
        logger.debug("quarantined_workflows_retrieved", count=len(responses))
        return responses
    except Exception as e:
        logger.error("quarantined_workflows_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve quarantined workflows: {e}"
        )


@router.post("/{document_id}/resume", response_model=InvoiceUploadResponse)
async def resume_workflow(
    document_id: str,
    request: WorkflowResumeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Resume a quarantined workflow with human feedback."""
    user_id = current_user["id"]
    logger.debug(
        "workflow_resume_requested",
        document_id=document_id,
        approved=request.approved,
        user_id=user_id,
    )
    try:
        human_feedback = {
            "approved": request.approved,
            "corrections": request.corrections or {},
            "notes": request.notes,
        }
        final_state = get_workflow_manager().resume_workflow(
            document_id, human_feedback, user_id=user_id
        )
        extracted_data = final_state.get("extracted_data", {})
        anomaly_dicts = final_state.get("anomalies", [])
        return InvoiceUploadResponse(
            success=final_state.get("status") == "completed",
            message=f"Workflow resumed: {final_state.get('status')}",
            invoice_id=final_state.get("neo4j_id"),
            invoice_number=extracted_data.get("invoice_number"),
            amount=extracted_data.get("total_amount"),
            line_items_count=len(extracted_data.get("line_items", [])),
            validation_anomalies=[
                ValidationAnomalyResponse(**a) for a in anomaly_dicts
            ],
            processing_time_seconds=final_state.get("processing_time_ms", 0) / 1000.0,
            workflow_id=document_id,
            retry_count=final_state.get("retry_count", 0),
            risk_level=final_state.get("risk_level"),
            requires_review=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("workflow_resume_failed", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {e}")


@router.get("/{document_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    document_id: str, current_user: dict = Depends(get_current_user)
):
    """Get current workflow status."""
    user_id = current_user["id"]
    logger.debug("workflow_status_requested", document_id=document_id, user_id=user_id)
    try:
        workflow = get_workflow_manager().get_workflow_status(document_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        stored_uid = workflow.get("user_id")
        if stored_uid and stored_uid != user_id:
            raise HTTPException(status_code=403, detail="Workflow not found")
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


@router.get("")
async def list_workflows(
    status: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """List all workflows, optionally filtered by status."""
    user_id = current_user["id"]
    logger.debug("workflows_list_requested", status=status, limit=limit, user_id=user_id)
    try:
        return get_workflow_manager().list_workflows(
            status=status, limit=limit, user_id=user_id
        )
    except Exception as e:
        logger.error("workflows_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list workflows: {e}")


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str, current_user: dict = Depends(get_current_user)
):
    """Get detailed workflow information by ID."""
    user_id = current_user["id"]
    logger.debug("workflow_get_requested", workflow_id=workflow_id, user_id=user_id)
    try:
        workflow = get_workflow_manager().get_workflow_status(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        stored_uid = workflow.get("user_id")
        if stored_uid and stored_uid != user_id:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow
    except HTTPException:
        raise
    except Exception as e:
        logger.error("workflow_get_failed", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get workflow: {e}")
