"""
Unit tests for PlannerAgent.

Tests:
- analyze() with different query types (generic, execution, clarification)
- execution_mode selection (one_way vs react)
- retry_with_feedback() for validation failures
- plan_next_step() for ReAct mode
"""

import pytest
from unittest.mock import Mock, patch

from backend.agents.multi_agent.planner_agent import PlannerAgent


@pytest.fixture
def planner_agent():
    """Create PlannerAgent with mocked OpenAIClient."""
    with patch("backend.agents.multi_agent.planner_agent.OpenAIClient") as mock_openai_cls:
        mock_openai = Mock()
        mock_openai_cls.return_value = mock_openai
        agent = PlannerAgent()
        agent.llm = mock_openai
        yield agent


class TestAnalyze:
    """Test query analysis and routing."""

    def test_analyze_generic_response(self, planner_agent):
        """Test routing to generic_response for greetings."""
        planner_agent.llm.extract_json.return_value = {
            "route": "generic_response",
            "execution_mode": None,
            "reasoning": "User is greeting",
            "response": "Hello! I'm your AI assistant for financial risk management. How can I help you today?",
        }

        result = planner_agent.analyze("Hello!", history=[])

        assert result["route"] == "generic_response"
        assert result["execution_mode"] is None
        assert "response" in result
        assert "Hello" in result["response"]

        # Verify LLM was called
        planner_agent.llm.extract_json.assert_called_once()

    def test_analyze_execution_plan_one_way(self, planner_agent):
        """Test routing to execution_plan with one_way mode for simple query."""
        planner_agent.llm.extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Simple query, all steps known upfront",
            "plan": {
                "intent": "Show invoices over $50k",
                "one_way": {
                    "steps": [
                        {"tool": "CypherQueryTool", "action": "Find invoices > $50000"},
                        {"tool": "CalculatorTool", "action": "Sum total amounts"},
                    ]
                },
            },
        }

        result = planner_agent.analyze("Show me invoices over $50k", history=[])

        assert result["route"] == "execution_plan"
        assert result["execution_mode"] == "one_way"
        assert "plan" in result
        assert result["plan"]["intent"] == "Show invoices over $50k"
        assert len(result["plan"]["one_way"]["steps"]) == 2

    def test_analyze_execution_plan_react(self, planner_agent):
        """Test routing to execution_plan with react mode for complex query."""
        planner_agent.llm.extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "react",
            "reasoning": "Multi-step query with dependencies",
            "plan": {
                "intent": "Find contractor with highest variance on most expensive project",
                "react": {
                    "initial_step": {
                        "tool": "CypherQueryTool",
                        "action": "Find most expensive project",
                    },
                    "strategy": "Find project → get contractors → calculate variance → identify highest",
                },
            },
        }

        result = planner_agent.analyze(
            "Which contractor has the highest variance on the most expensive project?",
            history=[],
        )

        assert result["route"] == "execution_plan"
        assert result["execution_mode"] == "react"
        assert "react" in result["plan"]
        assert "initial_step" in result["plan"]["react"]
        assert "strategy" in result["plan"]["react"]

    def test_analyze_clarification(self, planner_agent):
        """Test routing to clarification for ambiguous query."""
        planner_agent.llm.extract_json.return_value = {
            "route": "clarification",
            "execution_mode": None,
            "reasoning": "Query is ambiguous, need more details",
            "response": "Could you clarify which invoice you're referring to? Please provide an invoice number or contractor name.",
        }

        result = planner_agent.analyze("Show me the invoice", history=[])

        assert result["route"] == "clarification"
        assert "response" in result
        assert "clarify" in result["response"].lower()

    def test_analyze_with_conversation_history(self, planner_agent):
        """Test that conversation history is passed to LLM."""
        history = [
            {"role": "user", "content": "What's the budget for Project Alpha?"},
            {"role": "assistant", "content": "The budget is $500,000."},
        ]

        planner_agent.llm.extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Follow-up query using context",
            "plan": {
                "intent": "Calculate variance for Project Alpha",
                "one_way": {"steps": [{"tool": "CalculatorTool", "action": "Calculate variance"}]},
            },
        }

        result = planner_agent.analyze("What's the variance?", history=history)

        # Verify LLM was called with history
        call_args = planner_agent.llm.extract_json.call_args
        assert "history" in str(call_args) or "History" in str(call_args)


class TestRetryWithFeedback:
    """Test retry logic after validation failure."""

    def test_retry_with_different_approach(self, planner_agent):
        """Test creating new plan after validation failure."""
        previous_plan = {
            "intent": "Find invoices over $50k",
            "one_way": {
                "steps": [{"tool": "CypherQueryTool", "action": "Find invoices > $50000"}]
            },
        }

        validation_feedback = {
            "issues": ["No results returned from tool execution"],
            "retry_suggestion": "Try using VectorSearchTool instead",
        }

        planner_agent.llm.extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Switching to vector search as suggested",
            "plan": {
                "intent": "Find invoices over $50k using vector search",
                "one_way": {
                    "steps": [{"tool": "VectorSearchTool", "action": "Search for high-value invoices"}]
                },
            },
        }

        result = planner_agent.retry_with_feedback(
            user_query="Show me invoices over $50k",
            previous_plan=previous_plan,
            validation_feedback=validation_feedback,
            retry_count=0,
        )

        assert result["route"] == "execution_plan"
        assert result["plan"]["one_way"]["steps"][0]["tool"] == "VectorSearchTool"

        # Verify LLM was called with feedback
        call_args = planner_agent.llm.extract_json.call_args
        prompt = str(call_args)
        assert "failed validation" in prompt.lower() or "retry" in prompt.lower()

    def test_retry_route_to_clarification(self, planner_agent):
        """Test routing to clarification when retry can't fix issue."""
        previous_plan = {
            "intent": "Get data that doesn't exist",
            "one_way": {"steps": [{"tool": "CypherQueryTool", "action": "Find non-existent data"}]},
        }

        validation_feedback = {
            "issues": ["Data doesn't exist in system"],
            "retry_suggestion": "Ask user for clarification or different query",
        }

        planner_agent.llm.extract_json.return_value = {
            "route": "clarification",
            "execution_mode": None,
            "reasoning": "Can't find the requested data, need user input",
            "response": "I couldn't find that data in the system. Could you provide more details or try a different query?",
        }

        result = planner_agent.retry_with_feedback(
            user_query="Show me the data",
            previous_plan=previous_plan,
            validation_feedback=validation_feedback,
            retry_count=1,
        )

        assert result["route"] == "clarification"
        assert "response" in result


class TestPlanNextStep:
    """Test ReAct mode next step planning."""

    def test_plan_next_step_continue(self, planner_agent):
        """Test planning next step when more work needed."""
        completed_steps = [
            {
                "tool": "CypherQueryTool",
                "action": "Find most expensive project",
                "result": {"project_id": "PRJ-001", "name": "Tower Construction"},
            }
        ]

        current_results = {
            "results": [{"status": "success", "data": {"project_id": "PRJ-001"}}]
        }

        planner_agent.llm.extract_json.return_value = {
            "continue": True,
            "reasoning": "Need to find contractors for this project",
            "next_step": {
                "tool": "CypherQueryTool",
                "action": "Find contractors for project PRJ-001",
                "depends_on": "Step 1: Find most expensive project",
            },
        }

        result = planner_agent.plan_next_step(
            user_query="Which contractor has highest variance on most expensive project?",
            completed_steps=completed_steps,
            current_results=current_results,
            strategy="Find project → get contractors → calculate variance",
        )

        assert result["continue"] is True
        assert "next_step" in result
        assert result["next_step"]["tool"] == "CypherQueryTool"

    def test_plan_next_step_finish(self, planner_agent):
        """Test finishing ReAct loop when enough data gathered."""
        completed_steps = [
            {"tool": "CypherQueryTool", "action": "Find project", "result": {"project_id": "PRJ-001"}},
            {"tool": "CypherQueryTool", "action": "Find contractors", "result": {"contractors": []}},
            {"tool": "CalculatorTool", "action": "Calculate variance", "result": {"variance": 15.5}},
        ]

        current_results = {
            "results": [{"status": "success", "data": {"highest_variance": "ABC Contractors"}}]
        }

        planner_agent.llm.extract_json.return_value = {
            "continue": False,
            "reasoning": "We have all the information needed to answer the question",
        }

        result = planner_agent.plan_next_step(
            user_query="Which contractor has highest variance?",
            completed_steps=completed_steps,
            current_results=current_results,
            strategy="Find project → get contractors → calculate variance",
        )

        assert result["continue"] is False
        assert "next_step" not in result or result.get("next_step") is None

    def test_plan_next_step_max_steps(self, planner_agent):
        """Test that ReAct stops at max steps."""
        # Simulate 5 completed steps (max)
        completed_steps = [{"step": i} for i in range(5)]

        planner_agent.llm.extract_json.return_value = {
            "continue": False,
            "reasoning": "Reached maximum steps",
        }

        result = planner_agent.plan_next_step(
            user_query="Complex query",
            completed_steps=completed_steps,
            current_results={},
            strategy="Multi-step strategy",
        )

        # Should stop due to max steps
        assert result["continue"] is False
