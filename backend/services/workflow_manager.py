"""High-level workflow execution and management service."""

import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.core.logging import get_logger

from backend.ingestion.pipeline.invoice_workflow import compile_workflow_with_checkpoints
from backend.storage.workflow_store import WorkflowStore
from backend.core.config import settings

logger = get_logger(__name__)


class WorkflowManager:
    """Manages LangGraph workflow execution and state."""

    def __init__(self):
        """Initialize workflow manager with compiled graph and storage."""
        self.workflow = compile_workflow_with_checkpoints()
        self.store = WorkflowStore()

    def execute_sync(self, pdf_path: Path, document_type: str = "invoice", user_id: str = "default_user") -> Dict[str, Any]:
        """
        Execute workflow synchronously (blocking).

        Args:
            pdf_path: Path to PDF file
            document_type: Type of document (invoice, contract, etc.)

        Returns:
            Final workflow state
        """
        document_id = str(uuid.uuid4())
        start_time = time.time()

        logger.debug(
            "workflow_execution_started",
            document_id=document_id,
            pdf_path=str(pdf_path),
        )

        # Initialize workflow state
        initial_state = {
            "document_id": document_id,
            "document_path": str(pdf_path),
            "document_type": document_type,
            "raw_text": None,
            "extracted_data": None,
            "validation_results": [],
            "anomalies": [],
            "critic_feedback": None,
            "retry_count": 0,
            "max_retries": settings.workflow_max_retries,
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
            "current_node": None,
        }

        # Execute workflow with checkpointing
        config = {"configurable": {"thread_id": document_id}}

        try:
            final_state = None
            current_node = None

            # Stream through workflow states
            for state_update in self.workflow.stream(initial_state, config):
                if state_update:
                    # LangGraph returns {node_name: state_updates}
                    current_node = list(state_update.keys())[0] if state_update else "unknown"

                    logger.debug(
                        "workflow_state_update",
                        document_id=document_id,
                        current_node=current_node,
                    )

            # Get the final accumulated state from the workflow
            # This contains ALL fields, not just the last node's updates
            final_state_snapshot = self.workflow.get_state(config)
            if final_state_snapshot and final_state_snapshot.values:
                final_state = dict(final_state_snapshot.values)

                # Ensure document_id and current_node are present
                final_state["document_id"] = document_id
                final_state["current_node"] = current_node

                # Persist final state
                self.store.save_workflow(document_id, final_state, user_id=user_id)

            # Calculate total processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            if final_state:
                # Add processing time
                final_state["processing_time_ms"] = processing_time_ms

                logger.debug(
                    "workflow_execution_complete",
                    document_id=document_id,
                    status=final_state.get("status"),
                    processing_time_ms=processing_time_ms,
                    current_node=final_state.get("current_node"),
                )

                return final_state
            else:
                raise RuntimeError("Workflow completed with no final state")

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)

            error_state = {
                **initial_state,
                "document_id": document_id,  # Ensure document_id is present
                "status": "failed",
                "error_history": [
                    {
                        "node": "workflow_manager",
                        "error": str(e),
                        "timestamp": time.time(),
                    }
                ],
                "processing_time_ms": processing_time_ms,
            }

            self.store.save_workflow(document_id, error_state, user_id=user_id)

            logger.error(
                "workflow_execution_failed",
                document_id=document_id,
                error=str(e),
            )

            return error_state

    def resume_workflow(
        self, document_id: str, human_feedback: Dict[str, Any], user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resume paused workflow with human corrections.

        Args:
            document_id: Document ID of quarantined workflow
            human_feedback: Human corrections/approval

        Returns:
            Final workflow state after resumption
        """
        logger.debug(
            "workflow_resume_started",
            document_id=document_id,
            feedback=human_feedback,
        )

        # Load existing state
        stored = self.store.get_workflow(document_id)

        if not stored:
            raise ValueError(f"Workflow not found: {document_id}")

        stored_user_id = stored.get("user_id")
        if user_id and stored_user_id and stored_user_id != user_id:
            raise PermissionError(f"Workflow {document_id} does not belong to this user")

        state = stored["state"]

        # Check if workflow is actually paused
        if not state.get("paused"):
            raise ValueError(f"Workflow is not paused: {document_id}")

        # Apply human feedback
        state["human_feedback"] = human_feedback
        state["paused"] = False

        # Handle approval
        if human_feedback.get("approved"):
            # Override anomalies and risk level if approved
            state["risk_level"] = "low"
            state["anomalies"] = []

            logger.debug(
                "workflow_approved_by_human",
                document_id=document_id,
            )
        elif human_feedback.get("corrections"):
            # Apply corrections to extracted_data
            corrections = human_feedback["corrections"]
            if state.get("extracted_data"):
                state["extracted_data"].update(corrections)

            # Reset retry count to allow re-validation
            state["retry_count"] = 0

            logger.debug(
                "workflow_corrections_applied",
                document_id=document_id,
                corrections=corrections,
            )

        # Resume execution from quarantine checkpoint
        config = {"configurable": {"thread_id": document_id}}

        try:
            current_node = None

            # Continue workflow from quarantine
            for state_update in self.workflow.stream(state, config):
                if state_update:
                    current_node = list(state_update.keys())[0] if state_update else "unknown"

            # Get the final accumulated state
            final_state_snapshot = self.workflow.get_state(config)
            if final_state_snapshot and final_state_snapshot.values:
                final_state = dict(final_state_snapshot.values)
                final_state["document_id"] = document_id
                final_state["current_node"] = current_node

                # Save final state (preserve original owner)
                self.store.save_workflow(document_id, final_state, user_id=stored_user_id)

                logger.debug(
                    "workflow_resume_complete",
                    document_id=document_id,
                    final_status=final_state.get("status"),
                    current_node=current_node,
                )

                return final_state
            else:
                # Fallback to original state
                state["document_id"] = document_id
                state["current_node"] = current_node
                return state

        except Exception as e:
            logger.error(
                "workflow_resume_failed",
                document_id=document_id,
                error=str(e),
            )

            error_state = {
                **state,
                "status": "failed",
                "error_history": state.get("error_history", []) + [
                    {
                        "node": "workflow_resume",
                        "error": str(e),
                        "timestamp": time.time(),
                    }
                ],
            }

            self.store.save_workflow(document_id, error_state, user_id=stored_user_id)

            return error_state

    def get_workflow_status(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current workflow state.

        Args:
            document_id: Document ID

        Returns:
            Workflow state or None if not found
        """
        return self.store.get_workflow(document_id)

    def get_quarantined_workflows(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workflows awaiting human review, scoped to the given user.

        Args:
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of quarantined workflow states
        """
        return self.store.get_all_quarantined(user_id=user_id)

    def get_workflows_by_status(self, status: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workflows with a specific status, scoped to the given user.

        Args:
            status: Workflow status
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of workflow states
        """
        return self.store.get_all_by_status(status, user_id=user_id)

    def list_workflows(self, status: Optional[str] = None, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all workflows, optionally filtered by status and owner.

        Args:
            status: Optional status filter
            limit: Maximum number of workflows to return
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of workflow states
        """
        if status:
            workflows = self.store.get_all_by_status(status, user_id=user_id)
        else:
            workflows = self.store.get_all_workflows(user_id=user_id)

        # Sort by created_at descending (newest first)
        workflows.sort(key=lambda w: w.get("created_at", ""), reverse=True)

        # Apply limit
        return workflows[:limit]
