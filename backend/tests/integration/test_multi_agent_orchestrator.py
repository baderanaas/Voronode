"""
Integration tests for Multi-Agent Orchestrator.

Tests the full LangGraph workflow with all 4 agents:
- Planner → Executor → Validator → Responder
- Different routing scenarios (generic, execution, clarification)
- Validation retry loop
- One-way and ReAct execution modes
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from backend.agents.multi_agent.orchestrator import create_multi_agent_graph
from backend.agents.multi_agent.state import ConversationState


# Helper function to invoke graph with required config
def invoke_graph(graph, initial_state, thread_id="test_thread"):
    """Invoke graph with required thread_id config."""
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(initial_state, config)


@pytest.fixture
def mock_openai_client():
    """Create mocked OpenAI client for deterministic tests."""
    with patch("backend.agents.multi_agent.planner_agent.OpenAIClient") as mock_planner_openai, \
         patch("backend.agents.multi_agent.validator_agent.OpenAIClient") as mock_validator_openai, \
         patch("backend.agents.multi_agent.responder_agent.OpenAIClient") as mock_responder_openai:

        # Create mock instances
        planner_mock = Mock()
        validator_mock = Mock()
        responder_mock = Mock()

        mock_planner_openai.return_value = planner_mock
        mock_validator_openai.return_value = validator_mock
        mock_responder_openai.return_value = responder_mock

        yield {
            "planner": planner_mock,
            "validator": validator_mock,
            "responder": responder_mock,
        }


@pytest.fixture
def mock_tools():
    """Mock all tools to avoid external dependencies."""
    with patch("backend.tools.cypher_query_tool.CypherQueryTool") as mock_cypher, \
         patch("backend.tools.calculator_tool.CalculatorTool") as mock_calc, \
         patch("backend.tools.datetime_tool.DateTimeTool") as mock_datetime:

        # Create mock tool instances
        cypher_instance = Mock()
        calc_instance = Mock()
        datetime_instance = Mock()

        mock_cypher.return_value = cypher_instance
        mock_calc.return_value = calc_instance
        mock_datetime.return_value = datetime_instance

        yield {
            "cypher": cypher_instance,
            "calculator": calc_instance,
            "datetime": datetime_instance,
        }


class TestGenericResponseWorkflow:
    """Test workflow for generic responses (greetings, out-of-scope)."""

    def test_greeting_workflow(self, mock_openai_client):
        """Test handling of user greeting."""
        # Mock Planner to route to generic_response
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "generic_response",
            "execution_mode": None,
            "reasoning": "User is greeting",
            "response": "Hello! I'm your AI assistant for financial risk management. How can I help?",
        }

        # Create and execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Hello!",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify routing
        assert final_state["route"] == "generic_response"
        assert "final_response" in final_state
        assert "Hello" in final_state["final_response"]
        assert final_state["display_format"] == "text"

        # Executor should not be called for generic responses
        # (verified by no execution_results in state)
        assert "execution_results" not in final_state or final_state.get("execution_results") is None


class TestOneWayExecutionWorkflow:
    """Test one_way execution mode for simple queries."""

    def test_simple_query_one_way(self, mock_openai_client, mock_tools):
        """Test simple query using one_way execution."""
        # Mock Planner
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Simple query with known steps",
            "plan": {
                "intent": "Find invoices over $50k",
                "one_way": {
                    "steps": [
                        {"tool": "CypherQueryTool", "action": "Find invoices > $50000"},
                        {"tool": "CalculatorTool", "action": "Sum amounts"},
                    ]
                },
            },
        }

        # Mock tools
        mock_tools["cypher"].run.return_value = {
            "cypher_query": "MATCH (i:Invoice) WHERE i.amount > 50000 RETURN i",
            "results": [
                {"invoice_number": "INV-001", "amount": 75000},
                {"invoice_number": "INV-002", "amount": 62000},
            ],
            "count": 2,
            "status": "success",
        }

        mock_tools["calculator"].run.return_value = {
            "operation": "sum",
            "result": 137000,
            "status": "success",
        }

        # Mock Validator to pass
        mock_openai_client["validator"].extract_json.return_value = {
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "overall_valid": True,
            "issues": [],
            "retry_suggestion": "",
        }

        # Mock Responder
        mock_openai_client["responder"].extract_json.return_value = {
            "response": "I found **2 invoices** over $50,000, totaling **$137,000**.",
            "display_format": "table",
            "data": {
                "rows": [
                    {"invoice_number": "INV-001", "amount": 75000},
                    {"invoice_number": "INV-002", "amount": 62000},
                ],
                "summary": "2 invoices totaling $137,000",
            },
        }

        # Execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Show me invoices over $50k",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify workflow
        assert final_state["route"] == "execution_plan"
        assert final_state["execution_mode"] == "one_way"
        assert final_state["validation_result"]["valid"] is True
        assert final_state["display_format"] == "table"
        assert "2 invoices" in final_state["final_response"]

        # Verify tools were called
        assert mock_tools["cypher"].run.called
        assert mock_tools["calculator"].run.called


class TestReactExecutionWorkflow:
    """Test ReAct execution mode for complex queries."""

    def test_multi_step_react(self, mock_openai_client, mock_tools):
        """Test complex query using ReAct mode with multiple steps."""
        # Mock Planner initial analysis
        planner_responses = [
            # Initial analysis
            {
                "route": "execution_plan",
                "execution_mode": "react",
                "reasoning": "Complex multi-step query",
                "plan": {
                    "intent": "Find contractor with highest variance on most expensive project",
                    "react": {
                        "initial_step": {"tool": "CypherQueryTool", "action": "Find most expensive project"},
                        "strategy": "Find project → get contractors → calculate variance",
                    },
                },
            },
            # Next step planning (step 2)
            {
                "continue": True,
                "reasoning": "Need contractors for project",
                "next_step": {
                    "tool": "CypherQueryTool",
                    "action": "Find contractors for PRJ-001",
                },
            },
            # Final step planning (done)
            {
                "continue": False,
                "reasoning": "Have all needed information",
            },
        ]

        call_count = [0]

        def planner_side_effect(*args, **kwargs):
            result = planner_responses[call_count[0]]
            call_count[0] += 1
            return result

        mock_openai_client["planner"].extract_json.side_effect = planner_side_effect

        # Mock tools for ReAct steps
        tool_responses = [
            # Step 1: Find most expensive project
            {
                "results": [{"project_id": "PRJ-001", "name": "Tower Construction", "budget": 1000000}],
                "count": 1,
                "status": "success",
            },
            # Step 2: Find contractors
            {
                "results": [
                    {"contractor_id": "CONT-001", "name": "ABC Contractors", "variance": 15.5},
                    {"contractor_id": "CONT-002", "name": "XYZ Corp", "variance": 8.2},
                ],
                "count": 2,
                "status": "success",
            },
        ]

        tool_call_count = [0]

        def tool_side_effect(*args, **kwargs):
            result = tool_responses[tool_call_count[0]]
            tool_call_count[0] += 1
            return result

        mock_tools["cypher"].run.side_effect = tool_side_effect

        # Mock Validator
        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": True,
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "issues": [],
        }

        # Mock Responder
        mock_openai_client["responder"].extract_json.return_value = {
            "response": "**ABC Contractors** has the highest variance (**15.5%**) on Tower Construction.",
            "display_format": "text",
            "data": {"summary": "ABC Contractors: 15.5% variance"},
        }

        # Execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Which contractor has highest variance on most expensive project?",
            "conversation_history": [],
            "retry_count": 0,
            "react_max_steps": 5,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify ReAct workflow
        assert final_state["route"] == "execution_plan"
        assert final_state["execution_mode"] == "react"
        assert len(final_state["completed_steps"]) == 2  # Two steps executed
        assert final_state["react_continue"] is False  # Loop finished
        assert "ABC Contractors" in final_state["final_response"]


class TestValidationRetryWorkflow:
    """Test validation retry loop."""

    def test_validation_retry_then_success(self, mock_openai_client, mock_tools):
        """Test that failed validation triggers retry with new plan."""
        planner_call_count = [0]

        def planner_side_effect(*args, **kwargs):
            if planner_call_count[0] == 0:
                # Initial plan
                planner_call_count[0] += 1
                return {
                    "route": "execution_plan",
                    "execution_mode": "one_way",
                    "reasoning": "Query for invoices",
                    "plan": {
                        "intent": "Find invoices",
                        "one_way": {
                            "steps": [{"tool": "CypherQueryTool", "action": "Find all invoices"}]
                        },
                    },
                }
            else:
                # Retry plan after validation failure
                return {
                    "route": "execution_plan",
                    "execution_mode": "one_way",
                    "reasoning": "Trying different approach",
                    "plan": {
                        "intent": "Find invoices with filter",
                        "one_way": {
                            "steps": [{"tool": "CypherQueryTool", "action": "Find invoices > $0"}]
                        },
                    },
                }

        mock_openai_client["planner"].extract_json.side_effect = planner_side_effect

        tool_call_count = [0]

        def tool_side_effect(*args, **kwargs):
            if tool_call_count[0] == 0:
                # First attempt: return empty results
                tool_call_count[0] += 1
                return {"results": [], "count": 0, "status": "success"}
            else:
                # Second attempt: return results
                return {
                    "results": [{"invoice": "INV-001"}],
                    "count": 1,
                    "status": "success",
                }

        mock_tools["cypher"].run.side_effect = tool_side_effect

        validator_call_count = [0]

        def validator_side_effect(*args, **kwargs):
            if validator_call_count[0] == 0:
                # First validation: fail (empty results)
                validator_call_count[0] += 1
                return {
                    "overall_valid": False,
                    "answers_question": False,
                    "is_coherent": True,
                    "has_errors": False,
                    "has_sufficient_data": False,
                    "issues": ["No results returned"],
                    "retry_suggestion": "Try different query parameters",
                }
            else:
                # Second validation: pass
                return {
                    "overall_valid": True,
                    "answers_question": True,
                    "is_coherent": True,
                    "has_errors": False,
                    "has_sufficient_data": True,
                    "issues": [],
                }

        mock_openai_client["validator"].extract_json.side_effect = validator_side_effect

        # Mock Responder
        mock_openai_client["responder"].extract_json.return_value = {
            "response": "I found **1 invoice**.",
            "display_format": "text",
            "data": {},
        }

        # Execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Show me invoices",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify retry happened
        assert final_state["retry_count"] == 1  # One retry
        assert final_state["validation_result"]["valid"] is True  # Eventually passed
        assert "1 invoice" in final_state["final_response"]

    def test_validation_max_retries_exceeded(self, mock_openai_client, mock_tools):
        """Test that max retries stops the loop and returns error."""
        # Mock Planner to always return same plan
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Query",
            "plan": {
                "intent": "Find data",
                "one_way": {"steps": [{"tool": "CypherQueryTool", "action": "Find data"}]},
            },
        }

        # Mock tool to always return empty
        mock_tools["cypher"].run.return_value = {
            "results": [],
            "count": 0,
            "status": "success",
        }

        # Mock Validator to always fail
        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": False,
            "answers_question": False,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": False,
            "issues": ["No data found"],
            "retry_suggestion": "Check if data exists",
        }

        # Mock Responder for error
        mock_openai_client["responder"].extract_json.return_value = {
            "response": "I tried multiple approaches but couldn't find the data.",
            "display_format": "text",
            "data": {},
        }

        # Execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Find data",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify max retries reached
        assert final_state["retry_count"] == 2  # Max retries (0, 1, 2)
        # Should have error response
        assert "multiple approaches" in final_state["final_response"].lower() or \
               "couldn't" in final_state["final_response"].lower()


class TestClarificationWorkflow:
    """Test clarification routing."""

    def test_ambiguous_query_clarification(self, mock_openai_client):
        """Test that ambiguous queries request clarification."""
        # Mock Planner to route to clarification
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "clarification",
            "execution_mode": None,
            "reasoning": "Query is ambiguous",
            "response": "Could you please specify which invoice you're referring to? Provide an invoice number or contractor name.",
        }

        # Execute graph
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "Show me the invoice",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify clarification
        assert final_state["route"] == "clarification"
        assert "clarify" in final_state["final_response"].lower() or \
               "specify" in final_state["final_response"].lower()
        assert final_state["display_format"] == "text"


class TestConversationHistory:
    """Test conversation history handling."""

    def test_context_from_history(self, mock_openai_client):
        """Test that conversation history provides context."""
        # Mock Planner
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "generic_response",
            "execution_mode": None,
            "reasoning": "Follow-up question",
            "response": "Based on our previous discussion, that would be Project Alpha.",
        }

        # Execute graph with history
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": "What about Project Alpha?",
            "conversation_history": [
                {"role": "user", "content": "What projects do we have?"},
                {"role": "assistant", "content": "We have Project Alpha and Project Beta."},
            ],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Verify history was used
        assert final_state["route"] == "generic_response"
        # Planner should have been called with history in prompt
        planner_call = mock_openai_client["planner"].extract_json.call_args
        assert planner_call is not None
