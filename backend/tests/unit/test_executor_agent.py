"""
Unit tests for ExecutorAgent.

Tests:
- Tool initialization and lazy loading
- execute_one_way() with multiple tools
- execute_react_step() for ReAct mode
- Error handling for tool failures
- Metadata tracking (execution time, tools used)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from backend.agents.multi_agent.executor_agent import ExecutorAgent


@pytest.fixture
def executor_agent():
    """Create ExecutorAgent with mocked tools."""
    # Create ExecutorAgent and manually override its tools
    agent = ExecutorAgent()

    # Create mock tools
    mock_cypher = Mock()
    mock_calc = Mock()
    mock_datetime = Mock()

    # Replace tools with mocks
    agent.tools = {
        "DateTimeTool": mock_datetime,
        "CypherQueryTool": mock_cypher,
        "CalculatorTool": mock_calc,
    }

    yield agent


class TestExecuteOneWay:
    """Test one_way execution mode."""

    def test_execute_one_way_single_tool(self, executor_agent):
        """Test executing single tool in one_way mode."""
        plan = {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Find invoices over $50k"}
            ]
        }

        # Mock tool response
        executor_agent.tools["CypherQueryTool"].run.return_value = {
            "cypher_query": "MATCH (i:Invoice) WHERE i.amount > 50000 RETURN i",
            "results": [{"invoice": "INV-001"}],
            "count": 1,
            "status": "success",
        }

        result = executor_agent.execute_one_way(plan, user_query="Show me invoices over $50k")

        assert len(result["results"]) == 1
        assert result["results"][0]["tool"] == "CypherQueryTool"
        assert result["results"][0]["status"] == "success"
        assert "execution_time" in result["metadata"]
        assert "tools_used" in result["metadata"]
        assert "CypherQueryTool" in result["metadata"]["tools_used"]

        # Verify tool was called
        executor_agent.tools["CypherQueryTool"].run.assert_called_once()

    def test_execute_one_way_multiple_tools(self, executor_agent):
        """Test executing multiple tools in sequence."""
        plan = {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Find invoices"},
                {"tool": "CalculatorTool", "action": "Sum amounts"},
            ]
        }

        # Mock tool responses
        executor_agent.tools["CypherQueryTool"].run.return_value = {
            "results": [{"invoice": "INV-001", "amount": 75000}],
            "count": 1,
            "status": "success",
        }

        executor_agent.tools["CalculatorTool"].run.return_value = {
            "operation": "sum",
            "result": 75000,
            "status": "success",
        }

        result = executor_agent.execute_one_way(plan, user_query="Calculate total invoice amount")

        assert len(result["results"]) == 2
        assert result["results"][0]["tool"] == "CypherQueryTool"
        assert result["results"][1]["tool"] == "CalculatorTool"
        assert all(r["status"] == "success" for r in result["results"])

        # Both tools should be in metadata
        assert len(result["metadata"]["tools_used"]) == 2

    def test_execute_one_way_tool_failure(self, executor_agent):
        """Test handling tool execution failure."""
        plan = {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Invalid query"}
            ]
        }

        # Mock tool to raise exception
        executor_agent.tools["CypherQueryTool"].run.side_effect = Exception("Connection error")

        result = executor_agent.execute_one_way(plan, user_query="Get data")

        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "failed"
        assert "error" in result["results"][0]
        # Check for user-friendly error message (enhanced behavior)
        assert "database" in result["results"][0]["error"].lower() or "trouble" in result["results"][0]["error"].lower()
        # Technical error is stored separately
        assert "technical_error" in result["results"][0]
        assert "Connection error" in result["results"][0]["technical_error"]

    def test_execute_one_way_unknown_tool(self, executor_agent):
        """Test handling unknown tool gracefully."""
        plan = {
            "steps": [
                {"tool": "NonExistentTool", "action": "Do something"}
            ]
        }

        result = executor_agent.execute_one_way(plan, user_query="Test")

        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "failed"
        assert "not found" in result["results"][0]["error"].lower()

    def test_execute_one_way_partial_success(self, executor_agent):
        """Test execution with some tools succeeding and some failing."""
        plan = {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Find data"},
                {"tool": "CalculatorTool", "action": "Calculate"},
            ]
        }

        # First tool succeeds, second fails
        executor_agent.tools["CypherQueryTool"].run.return_value = {
            "results": [{"data": "value"}],
            "status": "success",
        }
        executor_agent.tools["CalculatorTool"].run.side_effect = Exception("Math error")

        result = executor_agent.execute_one_way(plan, user_query="Get and calculate data")

        assert len(result["results"]) == 2
        assert result["results"][0]["status"] == "success"
        assert result["results"][1]["status"] == "failed"

    def test_execute_one_way_tracks_time(self, executor_agent):
        """Test that execution time is tracked."""
        plan = {
            "steps": [
                {"tool": "DateTimeTool", "action": "Get current date"}
            ]
        }

        executor_agent.tools["DateTimeTool"].run.return_value = {
            "current_date": "2025-02-11",
            "status": "success",
        }

        result = executor_agent.execute_one_way(plan, user_query="What's today's date?")

        assert "execution_time" in result["metadata"]
        assert result["metadata"]["execution_time"] >= 0


class TestExecuteReactStep:
    """Test ReAct mode step execution."""

    def test_execute_react_step_first_step(self, executor_agent):
        """Test executing first step in ReAct mode."""
        step = {
            "tool": "CypherQueryTool",
            "action": "Find most expensive project"
        }

        executor_agent.tools["CypherQueryTool"].run.return_value = {
            "results": [{"project_id": "PRJ-001", "name": "Tower", "budget": 1000000}],
            "count": 1,
            "status": "success",
        }

        result = executor_agent.execute_react_step(
            step=step,
            user_query="Which contractor has highest variance on most expensive project?",
            previous_results=[]
        )

        # execute_react_step returns a single result dict (not wrapped in "results" array)
        assert result["tool"] == "CypherQueryTool"
        assert result["status"] == "success"
        assert "result" in result

    def test_execute_react_step_with_context(self, executor_agent):
        """Test ReAct step using previous results as context."""
        step = {
            "tool": "CypherQueryTool",
            "action": "Find contractors for project PRJ-001",
            "depends_on": "Previous step: Find most expensive project"
        }

        previous_results = [
            {
                "tool": "CypherQueryTool",
                "result": {"results": [{"project_id": "PRJ-001"}]},
                "status": "success",
            }
        ]

        executor_agent.tools["CypherQueryTool"].run.return_value = {
            "results": [{"contractor": "ABC"}, {"contractor": "XYZ"}],
            "count": 2,
            "status": "success",
        }

        result = executor_agent.execute_react_step(
            step=step,
            user_query="Find contractors",
            previous_results=previous_results
        )

        # execute_react_step returns a single result dict
        assert result["status"] == "success"

        # Verify tool was called with context
        call_kwargs = executor_agent.tools["CypherQueryTool"].run.call_args.kwargs
        # Should have context parameter with previous results
        assert "context" in call_kwargs
        assert "previous_results" in call_kwargs["context"]

    def test_execute_react_step_failure(self, executor_agent):
        """Test ReAct step with tool failure."""
        step = {
            "tool": "CalculatorTool",
            "action": "Calculate variance"
        }

        executor_agent.tools["CalculatorTool"].run.side_effect = Exception("Invalid data")

        result = executor_agent.execute_react_step(
            step=step,
            user_query="Calculate variance",
            previous_results=[]
        )

        # execute_react_step returns a single result dict
        assert result["status"] == "failed"
        # Check for user-friendly error message (enhanced behavior)
        assert "calculation" in result["error"].lower() or "issue" in result["error"].lower()
        # Technical error is stored separately
        assert "technical_error" in result
        assert "Invalid data" in result["technical_error"]


class TestToolInitialization:
    """Test tool initialization and management."""

    def test_tools_initialized_lazily(self):
        """Test that tools can be initialized without errors."""
        # This will attempt to import all tools
        agent = ExecutorAgent()

        # Should have tools dictionary
        assert hasattr(agent, 'tools')
        assert isinstance(agent.tools, dict)
        # Should have at least some tools initialized (even if placeholders)
        assert len(agent.tools) > 0

    def test_missing_tool_handled_gracefully(self, executor_agent):
        """Test that missing tools are handled without crashing."""
        plan = {
            "steps": [
                {"tool": "UnavailableTool", "action": "Do something"}
            ]
        }

        # Should not raise exception
        result = executor_agent.execute_one_way(plan, user_query="Test")

        assert result["results"][0]["status"] == "failed"


class TestMetadataTracking:
    """Test metadata tracking during execution."""

    def test_metadata_includes_execution_time(self, executor_agent):
        """Test that metadata tracks execution time."""
        plan = {"steps": [{"tool": "DateTimeTool", "action": "Get date"}]}

        executor_agent.tools["DateTimeTool"].run.return_value = {"status": "success"}

        result = executor_agent.execute_one_way(plan, user_query="Test")

        assert "execution_time" in result["metadata"]
        assert isinstance(result["metadata"]["execution_time"], (int, float))
        assert result["metadata"]["execution_time"] >= 0

    def test_metadata_includes_tools_used(self, executor_agent):
        """Test that metadata tracks which tools were used."""
        plan = {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Query"},
                {"tool": "CalculatorTool", "action": "Calculate"},
            ]
        }

        executor_agent.tools["CypherQueryTool"].run.return_value = {"status": "success"}
        executor_agent.tools["CalculatorTool"].run.return_value = {"status": "success"}

        result = executor_agent.execute_one_way(plan, user_query="Test")

        assert "tools_used" in result["metadata"]
        assert "CypherQueryTool" in result["metadata"]["tools_used"]
        assert "CalculatorTool" in result["metadata"]["tools_used"]
        assert len(result["metadata"]["tools_used"]) == 2

    def test_metadata_tracks_failed_tools(self, executor_agent):
        """Test that metadata still includes tools that failed."""
        plan = {"steps": [{"tool": "CypherQueryTool", "action": "Query"}]}

        executor_agent.tools["CypherQueryTool"].run.side_effect = Exception("Error")

        result = executor_agent.execute_one_way(plan, user_query="Test")

        # Failed tool should still be in tools_used
        assert "CypherQueryTool" in result["metadata"]["tools_used"]
