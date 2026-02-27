"""
Upload Agent - Document ingestion engine.

Executes document upload steps from an upload_plan produced by PlannerAgent.
Handles InvoiceUploadTool, ContractUploadTool, and BudgetUploadTool.

No ReAct mode needed — uploads are deterministic, one-pass operations.
"""

from backend.core.logging import get_logger
import time
from typing import Dict, Any, List

logger = get_logger(__name__)


class UploadAgent:
    """
    Agent that executes document upload tools based on plan.

    Responsibilities:
    1. Initialize the three upload tools
    2. Execute steps sequentially from upload_plan
    3. Collect results in the same format as ExecutorAgent.execute_one_way()
    """

    def __init__(self):
        """Initialize UploadAgent with the three document ingestion tools."""
        self.tools: Dict[str, Any] = {}
        self._initialize_tools()

    def _initialize_tools(self):
        """Load the three upload tools."""
        try:
            from backend.agents.tools.invoice_upload_tool import InvoiceUploadTool
            self.tools["InvoiceUploadTool"] = InvoiceUploadTool()
        except ImportError:
            logger.warning("InvoiceUploadTool not available")

        try:
            from backend.agents.tools.contract_upload_tool import ContractUploadTool
            self.tools["ContractUploadTool"] = ContractUploadTool()
        except ImportError:
            logger.warning("ContractUploadTool not available")

        try:
            from backend.agents.tools.budget_upload_tool import BudgetUploadTool
            self.tools["BudgetUploadTool"] = BudgetUploadTool()
        except ImportError:
            logger.warning("BudgetUploadTool not available")

        logger.info("upload_agent_tools_initialized", tool_count=len(self.tools))

    def execute(
        self,
        plan: Dict[str, Any],
        user_query: str,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Execute all upload steps from plan sequentially.

        Args:
            plan: Upload plan from Planner (contains "steps" list)
            user_query: Original user query for context

        Returns:
            Same structure as ExecutorAgent.execute_one_way():
            {
                "results": [...],
                "status": "success" | "partial" | "failure",
                "metadata": {
                    "execution_mode": "upload",
                    "execution_time": 1.2,
                    "steps_completed": 2,
                    "steps_total": 2,
                    "tools_used": ["InvoiceUploadTool", "ContractUploadTool"]
                }
            }
        """
        steps = plan.get("steps", [])
        logger.info("upload_agent_execute_started", steps=len(steps))

        results: List[Dict[str, Any]] = []
        start_time = time.time()

        for idx, step in enumerate(steps):
            tool_name = step.get("tool", "")
            action = step.get("action", "")

            logger.info("upload_agent_step", step=idx + 1, tool=tool_name)

            tool = self.tools.get(tool_name)
            if not tool:
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "action": action,
                    "error": f"Tool '{tool_name}' not found in UploadAgent",
                    "status": "failed",
                })
                continue

            try:
                result = tool.run(query=user_query, action=action, user_id=user_id)
                step_status = result.get("status", "success")
                step_result = {
                    "step": idx + 1,
                    "tool": tool_name,
                    "action": action,
                    "result": result,
                    "status": step_status,
                }
                results.append(step_result)

                if step_status == "success":
                    logger.info("upload_agent_step_success", step=idx + 1, tool=tool_name)
                else:
                    logger.warning(
                        "upload_agent_step_failed",
                        step=idx + 1,
                        tool=tool_name,
                        error=result.get("error"),
                    )

            except Exception as e:
                logger.error(
                    "upload_agent_step_exception",
                    step=idx + 1,
                    tool=tool_name,
                    error=str(e),
                )
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "action": action,
                    "error": f"Unexpected error in {tool_name}: {e}",
                    "status": "failed",
                })

        execution_time = time.time() - start_time

        success_count = sum(1 for r in results if r["status"] == "success")
        if success_count == len(results) and len(results) > 0:
            overall_status = "success"
        elif success_count > 0:
            overall_status = "partial"
        else:
            overall_status = "failure"

        logger.info(
            "upload_agent_execute_complete",
            status=overall_status,
            steps_completed=success_count,
            steps_total=len(results),
            execution_time=execution_time,
        )

        return {
            "results": results,
            "status": overall_status,
            "metadata": {
                "execution_mode": "upload",
                "execution_time": execution_time,
                "steps_completed": success_count,
                "steps_total": len(results),
                "tools_used": [step.get("tool") for step in steps],
            },
        }
