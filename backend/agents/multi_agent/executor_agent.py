"""
Executor Agent - Tool execution engine.

Executes tools according to plans from PlannerAgent. Supports two execution modes:
- one_way: Execute all steps sequentially (for simple queries)
- react: Execute single step at a time with dynamic planning (for complex queries)

Enhanced with:
- Circuit breaker pattern for failing tools
- Timeout handling for long-running tools
- User-friendly error messages
- Graceful degradation
"""

import structlog
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from backend.core.circuit_breaker import ToolCircuitBreakerManager, CircuitOpenError

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

    def __init__(
        self,
        tool_timeout: int = 30,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_timeout: int = 60,
    ):
        """
        Initialize Executor with all available tools.

        Args:
            tool_timeout: Maximum seconds to wait for tool execution (default: 30)
            circuit_breaker_threshold: Failures before opening circuit (default: 3)
            circuit_breaker_timeout: Cooldown period in seconds (default: 60)
        """
        self.tools = {}
        self.tool_timeout = tool_timeout
        self.circuit_breaker_manager = ToolCircuitBreakerManager(
            failure_threshold=circuit_breaker_threshold,
            timeout=circuit_breaker_timeout,
        )
        self._executor = ThreadPoolExecutor(max_workers=5)
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

    def _execute_tool_with_protection(
        self,
        tool_name: str,
        tool: Any,
        user_query: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute tool with circuit breaker and timeout protection.

        Args:
            tool_name: Name of the tool
            tool: Tool instance
            user_query: Original user query
            action: Action to perform
            context: Optional context (for ReAct mode)

        Returns:
            Dict with result or error information
        """
        breaker = self.circuit_breaker_manager.get_breaker(tool_name)

        try:
            # Execute with circuit breaker protection
            def run_tool():
                kwargs = {"query": user_query, "action": action}
                if context:
                    kwargs["context"] = context
                return tool.run(**kwargs)

            # Execute with timeout using ThreadPoolExecutor
            future = self._executor.submit(breaker.call, run_tool)
            result = future.result(timeout=self.tool_timeout)

            return {
                "result": result,
                "status": "success",
            }

        except CircuitOpenError as e:
            # Circuit breaker is open - tool has been failing repeatedly
            logger.warning(
                "tool_circuit_open",
                tool=tool_name,
                error=str(e),
            )
            return {
                "error": self._user_friendly_error(tool_name, "circuit_open"),
                "error_type": "circuit_open",
                "status": "failed",
                "technical_error": str(e),
            }

        except FutureTimeoutError:
            # Tool exceeded timeout
            logger.error(
                "tool_timeout",
                tool=tool_name,
                timeout=self.tool_timeout,
            )
            return {
                "error": self._user_friendly_error(tool_name, "timeout"),
                "error_type": "timeout",
                "status": "failed",
                "technical_error": f"Tool exceeded {self.tool_timeout}s timeout",
            }

        except Exception as e:
            # General tool error
            error_type = type(e).__name__
            logger.error(
                "tool_execution_failed",
                tool=tool_name,
                error=str(e),
                error_type=error_type,
            )
            return {
                "error": self._user_friendly_error(tool_name, "general", str(e)),
                "error_type": "execution_error",
                "status": "failed",
                "technical_error": str(e),
            }

    def _user_friendly_error(
        self,
        tool_name: str,
        error_type: str,
        technical_msg: str = "",
    ) -> str:
        """
        Convert technical errors to user-friendly messages.

        Args:
            tool_name: Name of the tool that failed
            error_type: Type of error (circuit_open, timeout, general)
            technical_msg: Technical error message

        Returns:
            User-friendly error message
        """
        tool_descriptions = {
            "CypherQueryTool": "database query",
            "VectorSearchTool": "document search",
            "CalculatorTool": "calculation",
            "GraphExplorerTool": "data exploration",
            "ComplianceCheckTool": "compliance check",
            "DateTimeTool": "date/time operation",
            "WebSearchTool": "web search",
            "PythonREPLTool": "code execution",
        }

        tool_desc = tool_descriptions.get(tool_name, "operation")

        if error_type == "circuit_open":
            return (
                f"The {tool_desc} service is temporarily unavailable due to repeated errors. "
                f"Please try again in a minute or rephrase your question to use a different approach."
            )
        elif error_type == "timeout":
            return (
                f"The {tool_desc} took too long to complete. "
                f"Try simplifying your query or breaking it into smaller parts."
            )
        elif "not found" in technical_msg.lower() or "no results" in technical_msg.lower():
            return (
                f"I couldn't find any matching data for your query. "
                f"Try rephrasing or checking if the data exists in the system."
            )
        elif "connection" in technical_msg.lower():
            return (
                f"I'm having trouble connecting to the database. "
                f"Please try again in a moment."
            )
        else:
            # Generic error - still make it friendlier
            return (
                f"I encountered an issue while performing the {tool_desc}. "
                f"Please try rephrasing your question or contact support if this persists."
            )

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

            # Execute tool with protection (circuit breaker + timeout)
            execution_result = self._execute_tool_with_protection(
                tool_name=tool_name,
                tool=tool,
                user_query=user_query,
                action=action,
            )

            # Add step metadata
            step_result = {
                "step": idx + 1,
                "tool": tool_name,
                "action": action,
                **execution_result,
            }
            results.append(step_result)

            if execution_result["status"] == "success":
                logger.info("executor_step_success", step=idx + 1, tool=tool_name)
            else:
                logger.warning(
                    "executor_step_failed",
                    step=idx + 1,
                    tool=tool_name,
                    error_type=execution_result.get("error_type"),
                )

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

        # Execute tool with protection (circuit breaker + timeout)
        execution_result = self._execute_tool_with_protection(
            tool_name=tool_name,
            tool=tool,
            user_query=user_query,
            action=action,
            context={"previous_results": previous_results},
        )

        # Add tool and action to result
        result = {
            "tool": tool_name,
            "action": action,
            **execution_result,
        }

        if execution_result["status"] == "success":
            logger.info("executor_react_step_success", tool=tool_name)
        else:
            logger.warning(
                "executor_react_step_failed",
                tool=tool_name,
                error_type=execution_result.get("error_type"),
            )

        return result
