"""
Executor Agent - Tool execution engine.

Executes tools according to plans from PlannerAgent. Supports two execution modes:
- one_way: Execute all steps sequentially (for simple queries)
- react: Execute single step at a time with dynamic planning (for complex queries)
"""

import structlog
import time
from typing import Dict, Any, List

logger = structlog.get_logger()


class ExecutorAgent:
    """
    Agent that executes tools based on plan.

    Responsibilities:
    1. Execute tools in one_way mode (all steps at once)
    2. Execute single step in react mode
    3. Handle tool errors gracefully
    4. Track execution metadata (time, tools used, success rate)
    """

    def __init__(self):
        """
        Initialize Executor with all available tools.

        Tools will be imported lazily to avoid circular dependencies.
        """
        self.tools = {}
        self._initialize_tools()

    def _initialize_tools(self):
        """
        Initialize all tools.

        Tools are loaded lazily and will be properly implemented in Tasks #14-15.
        For now, we create placeholders that will be replaced with actual implementations.
        """
        # Import tools (will be implemented in later tasks)
        try:
            from backend.tools.cypher_query_tool import CypherQueryTool
            self.tools["CypherQueryTool"] = CypherQueryTool()
        except ImportError:
            logger.warning("CypherQueryTool not yet implemented")
            self.tools["CypherQueryTool"] = self._create_placeholder_tool("CypherQueryTool")

        try:
            from backend.tools.vector_search_tool import VectorSearchTool
            self.tools["VectorSearchTool"] = VectorSearchTool()
        except ImportError:
            logger.warning("VectorSearchTool not yet implemented")
            self.tools["VectorSearchTool"] = self._create_placeholder_tool("VectorSearchTool")

        try:
            from backend.tools.calculator_tool import CalculatorTool
            self.tools["CalculatorTool"] = CalculatorTool()
        except ImportError:
            logger.warning("CalculatorTool not yet implemented")
            self.tools["CalculatorTool"] = self._create_placeholder_tool("CalculatorTool")

        try:
            from backend.tools.graph_explorer_tool import GraphExplorerTool
            self.tools["GraphExplorerTool"] = GraphExplorerTool()
        except ImportError:
            logger.warning("GraphExplorerTool not yet implemented")
            self.tools["GraphExplorerTool"] = self._create_placeholder_tool("GraphExplorerTool")

        try:
            from backend.tools.compliance_check_tool import ComplianceCheckTool
            self.tools["ComplianceCheckTool"] = ComplianceCheckTool()
        except ImportError:
            logger.warning("ComplianceCheckTool not yet implemented")
            self.tools["ComplianceCheckTool"] = self._create_placeholder_tool("ComplianceCheckTool")

        try:
            from backend.tools.datetime_tool import DateTimeTool
            self.tools["DateTimeTool"] = DateTimeTool()
        except ImportError:
            logger.warning("DateTimeTool not yet implemented")
            self.tools["DateTimeTool"] = self._create_placeholder_tool("DateTimeTool")

        try:
            from backend.tools.web_search_tool import WebSearchTool
            self.tools["WebSearchTool"] = WebSearchTool()
        except ImportError:
            logger.warning("WebSearchTool not yet implemented")
            self.tools["WebSearchTool"] = self._create_placeholder_tool("WebSearchTool")

        try:
            from backend.tools.python_repl_tool import PythonREPLTool
            self.tools["PythonREPLTool"] = PythonREPLTool()
        except ImportError:
            logger.warning("PythonREPLTool not yet implemented")
            self.tools["PythonREPLTool"] = self._create_placeholder_tool("PythonREPLTool")

        logger.info("executor_tools_initialized", tool_count=len(self.tools))

    def _create_placeholder_tool(self, tool_name: str):
        """Create a placeholder tool for tools not yet implemented."""
        class PlaceholderTool:
            def __init__(self, name):
                self.name = name

            def run(self, **kwargs):
                return {
                    "error": f"{self.name} not yet implemented",
                    "status": "placeholder"
                }

        return PlaceholderTool(tool_name)

    def execute_one_way(self, plan: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """
        Execute all steps sequentially (one-way mode).

        Used for simple queries where all steps can be planned upfront
        and don't depend on intermediate results.

        Args:
            plan: Execution plan from Planner (contains "steps" list)
            user_query: Original user query for context

        Returns:
            {
                "results": [...],  # List of step results
                "status": "success" | "partial" | "failure",
                "metadata": {
                    "execution_mode": "one_way",
                    "execution_time": 1.2,
                    "steps_completed": 2,
                    "steps_total": 2,
                    "tools_used": ["CypherQueryTool", "CalculatorTool"]
                }
            }
        """
        logger.info("executor_one_way_started", steps=len(plan.get("steps", [])))

        results = []
        start_time = time.time()
        steps = plan.get("steps", [])

        for idx, step in enumerate(steps):
            tool_name = step["tool"]
            action = step["action"]

            logger.info("executor_step", step=idx + 1, tool=tool_name)

            # Get tool
            tool = self.tools.get(tool_name)
            if not tool:
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "error": f"Tool {tool_name} not found",
                    "status": "failed",
                })
                continue

            # Execute tool
            try:
                result = tool.run(
                    query=user_query,
                    action=action,
                )
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "action": action,
                    "result": result,
                    "status": "success",
                })
                logger.info("executor_step_success", step=idx + 1, tool=tool_name)

            except Exception as e:
                logger.error("executor_step_failed", step=idx + 1, tool=tool_name, error=str(e))
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "action": action,
                    "error": str(e),
                    "status": "failed",
                })

        execution_time = time.time() - start_time

        # Determine overall status
        success_count = sum(1 for r in results if r["status"] == "success")
        if success_count == len(results):
            overall_status = "success"
        elif success_count > 0:
            overall_status = "partial"
        else:
            overall_status = "failure"

        logger.info(
            "executor_one_way_complete",
            status=overall_status,
            steps_completed=success_count,
            steps_total=len(results),
            execution_time=execution_time,
        )

        return {
            "results": results,
            "status": overall_status,
            "metadata": {
                "execution_mode": "one_way",
                "execution_time": execution_time,
                "steps_completed": success_count,
                "steps_total": len(results),
                "tools_used": [step["tool"] for step in steps],
            },
        }

    def execute_react_step(
        self,
        step: Dict[str, Any],
        user_query: str,
        previous_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Execute single step in ReAct mode.

        Used for complex queries where each step depends on previous results
        and dynamic planning is needed.

        Args:
            step: Single step to execute (contains "tool" and "action")
            user_query: Original user query for context
            previous_results: Results from previous steps (for context)

        Returns:
            {
                "tool": "CypherQueryTool",
                "action": "Find most expensive project",
                "result": {...},
                "status": "success" | "failed",
                "error": "..." # If failed
            }
        """
        tool_name = step["tool"]
        action = step["action"]

        logger.info("executor_react_step", tool=tool_name, action=action[:50])

        # Get tool
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "tool": tool_name,
                "action": action,
                "error": f"Tool {tool_name} not found",
                "status": "failed",
            }

        # Execute tool with context
        try:
            # Pass previous results as context for tools that need it
            result = tool.run(
                query=user_query,
                action=action,
                context={"previous_results": previous_results},
            )

            logger.info("executor_react_step_success", tool=tool_name)

            return {
                "tool": tool_name,
                "action": action,
                "result": result,
                "status": "success",
            }

        except Exception as e:
            logger.error("executor_react_step_failed", tool=tool_name, error=str(e))

            return {
                "tool": tool_name,
                "action": action,
                "error": str(e),
                "status": "failed",
            }
