"""
WorkflowTool - Interact with document processing workflows.

Allows AI to manage workflows: list quarantined items, check status, and resume paused workflows.
"""

import json
import structlog
from typing import Dict, Any, List, Optional

from backend.services.workflow_manager import WorkflowManager

logger = structlog.get_logger()


class WorkflowTool:
    """
    Tool for interacting with the document processing workflow system.

    This tool allows the AI to:
    - List workflows that are paused for human review (quarantined)
    - Get the status of a specific workflow by its ID
    - Resume a quarantined workflow with approval or corrections
    """

    def __init__(self):
        """Initialize the WorkflowTool."""
        self.workflow_manager = WorkflowManager()
        logger.info("workflow_tool_initialized")

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for the tool.

        Args:
            query: User's original query
            action: The specific function to perform (format: "action_name|param1=value1|param2=value2")
                Supported actions:
                - "list_quarantined"
                - "get_status|workflow_id=<id>"
                - "resume|workflow_id=<id>|approved=<true/false>|corrections={...}|notes=..."
            context: Previous results for ReAct mode

        Returns:
            A dictionary containing the result of the action
        """
        logger.info("workflow_tool_run", action=action[:100])

        # Parse action into command and parameters
        parsed = self._parse_action(action)
        command = parsed["command"]
        params = parsed["params"]

        if command == "list_quarantined":
            return self._get_quarantined_workflows()

        elif command == "get_status":
            if "workflow_id" not in params:
                return {
                    "error": "Missing 'workflow_id' for get_status action",
                    "status": "failed",
                }
            return self._get_workflow_status(workflow_id=params["workflow_id"])

        elif command == "resume":
            required_args = ["workflow_id", "approved"]
            missing = [arg for arg in required_args if arg not in params]
            if missing:
                return {
                    "error": f"Missing required parameters: {', '.join(missing)}",
                    "status": "failed",
                }

            # Parse approved as boolean
            approved = params["approved"].lower() in ["true", "yes", "1", "approve"]

            raw_corrections = params.get("corrections", "{}")
            try:
                corrections = json.loads(raw_corrections) if isinstance(raw_corrections, str) else raw_corrections
            except json.JSONDecodeError:
                corrections = {}

            return self._resume_workflow(
                workflow_id=params["workflow_id"],
                approved=approved,
                corrections=corrections,
                notes=params.get("notes", ""),
            )

        else:
            return {
                "error": f"Unsupported action '{command}'. Supported: list_quarantined, get_status, resume",
                "status": "failed",
            }

    def _parse_action(self, action: str) -> Dict[str, Any]:
        """
        Parse action string into command and parameters.

        Format: "command|param1=value1|param2=value2"
        Example: "resume|workflow_id=abc123|approved=true|notes=looks good"

        Args:
            action: Action string

        Returns:
            {"command": "resume", "params": {"workflow_id": "abc123", "approved": "true", "notes": "looks good"}}
        """
        parts = action.split("|")
        command = parts[0].strip()
        params = {}

        last_key = None
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                last_key = key.strip()
                params[last_key] = value
            elif last_key is not None:
                # Value contained a pipe character — re-join it
                params[last_key] += "|" + part

        return {"command": command, "params": params}

    def _get_quarantined_workflows(self) -> Dict[str, Any]:
        """Retrieve workflows awaiting human review."""
        try:
            workflows = self.workflow_manager.get_quarantined_workflows()

            if not workflows:
                return {
                    "status": "success",
                    "result": "There are no workflows awaiting review",
                    "count": 0,
                    "workflows": [],
                }

            # Simplify the output for the AI
            simplified_workflows = []
            for wf in workflows:
                state = wf.get("state", {})
                simplified_workflows.append({
                    "workflow_id": wf.get("document_id"),
                    "status": wf.get("status"),
                    "risk_level": state.get("risk_level"),
                    "pause_reason": state.get("pause_reason"),
                    "created_at": wf.get("created_at"),
                    "document_type": state.get("document_type"),
                    "extracted_data": state.get("extracted_data", {}),
                    "anomalies": state.get("anomalies", []),
                })

            logger.info("workflow_tool_quarantined_list", count=len(simplified_workflows))

            return {
                "status": "success",
                "count": len(simplified_workflows),
                "workflows": simplified_workflows,
            }

        except Exception as e:
            logger.error("workflow_tool_get_quarantined_failed", error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to retrieve quarantined workflows: {e}",
            }

    def _get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get the status of a specific workflow."""
        try:
            workflow = self.workflow_manager.get_workflow_status(workflow_id)

            if not workflow:
                return {
                    "status": "failed",
                    "error": f"Workflow with ID '{workflow_id}' not found",
                }

            # Simplify workflow state for AI consumption
            state = workflow.get("state", {})
            simplified = {
                "workflow_id": workflow.get("document_id"),
                "status": workflow.get("status"),
                "created_at": workflow.get("created_at"),
                "updated_at": workflow.get("updated_at"),
                "document_type": state.get("document_type"),
                "current_node": state.get("current_node"),
                "risk_level": state.get("risk_level"),
                "paused": state.get("paused", False),
                "pause_reason": state.get("pause_reason"),
                "processing_time_ms": state.get("processing_time_ms"),
                "retry_count": state.get("retry_count", 0),
                "anomalies": state.get("anomalies", []),
            }

            logger.info("workflow_tool_status_retrieved", workflow_id=workflow_id)

            return {
                "status": "success",
                "workflow": simplified,
            }

        except Exception as e:
            logger.error("workflow_tool_get_status_failed", workflow_id=workflow_id, error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to get status for workflow '{workflow_id}': {e}",
            }

    def _resume_workflow(
        self,
        workflow_id: str,
        approved: bool,
        corrections: Dict[str, Any],
        notes: str,
    ) -> Dict[str, Any]:
        """Resume a quarantined workflow."""
        try:
            human_feedback = {
                "approved": approved,
                "corrections": corrections,
                "notes": notes,
            }

            final_state = self.workflow_manager.resume_workflow(workflow_id, human_feedback)

            logger.info(
                "workflow_tool_resumed",
                workflow_id=workflow_id,
                approved=approved,
                final_status=final_state.get("status"),
            )

            return {
                "status": "success",
                "result": f"Workflow '{workflow_id}' resumed successfully",
                "final_status": final_state.get("status"),
                "workflow_id": workflow_id,
            }

        except ValueError as e:
            # Handles not found or not paused errors
            logger.warning("workflow_tool_resume_validation_error", workflow_id=workflow_id, error=str(e))
            return {
                "status": "failed",
                "error": str(e),
            }

        except Exception as e:
            logger.error("workflow_tool_resume_failed", workflow_id=workflow_id, error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to resume workflow '{workflow_id}': {e}",
            }
