"""
Integration tests for Multi-Agent Orchestrator.

Tests the full LangGraph workflow with all 4 agents:
- Planner → Executor → Validator → Responder
- Different routing scenarios (generic, execution, clarification)
- Validation retry loop
- One-way and ReAct execution modes
"""

import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from backend.agents.orchestrator import create_multi_agent_graph
from backend.agents.state import ConversationState


# Helper function to invoke graph with required config
def invoke_graph(graph, initial_state, thread_id="test_thread"):
    """Invoke graph with required thread_id config."""
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(initial_state, config)


@pytest.fixture
def mock_openai_client():
    """Create mocked LLM clients for deterministic tests."""
    with patch("backend.agents.planner_agent.GeminiClient") as mock_planner_gemini, \
         patch("backend.agents.validator_agent.OpenAIClient") as mock_validator_openai, \
         patch("backend.agents.responder_agent.OpenAIClient") as mock_responder_openai:

        # Create mock instances
        planner_mock = Mock()
        validator_mock = Mock()
        responder_mock = Mock()

        mock_planner_gemini.return_value = planner_mock
        mock_validator_openai.return_value = validator_mock
        mock_responder_openai.return_value = responder_mock

        yield {
            "planner": planner_mock,
            "validator": validator_mock,
            "responder": responder_mock,
        }


@pytest.fixture
def mock_tools():
    """Mock all tools to avoid external service dependencies."""
    with patch("backend.agents.tools.cypher_query_tool.CypherQueryTool") as mock_cypher, \
         patch("backend.agents.tools.calculator_tool.CalculatorTool") as mock_calc, \
         patch("backend.agents.tools.datetime_tool.DateTimeTool") as mock_datetime, \
         patch("backend.agents.tools.vector_search_tool.VectorSearchTool") as mock_vector, \
         patch("backend.agents.tools.graph_explorer_tool.GraphExplorerTool") as mock_graph, \
         patch("backend.agents.tools.compliance_check_tool.ComplianceCheckTool") as mock_compliance, \
         patch("backend.agents.tools.web_search_tool.WebSearchTool") as mock_web, \
         patch("backend.agents.tools.python_repl_tool.PythonREPLTool") as mock_repl:

        # Create mock tool instances
        cypher_instance = Mock()
        calc_instance = Mock()
        datetime_instance = Mock()

        mock_cypher.return_value = cypher_instance
        mock_calc.return_value = calc_instance
        mock_datetime.return_value = datetime_instance
        mock_vector.return_value = Mock()
        mock_graph.return_value = Mock()
        mock_compliance.return_value = Mock()
        mock_web.return_value = Mock()
        mock_repl.return_value = Mock()

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
        assert len(final_state["final_response"]) > 0
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


class TestUploadWorkflow:
    """Test upload_plan route through UploadAgent → validator → responder."""

    def test_invoice_upload_full_path(self, mock_openai_client):
        """Test that upload_plan routes to UploadAgent and produces a confirmation."""
        with patch("backend.agents.orchestrator.UploadAgent") as mock_upload_cls:
            mock_upload = Mock()
            mock_upload_cls.return_value = mock_upload
            mock_upload.execute.return_value = {
                "results": [
                    {
                        "step": 1,
                        "tool": "InvoiceUploadTool",
                        "action": "Process invoice /tmp/invoice.pdf",
                        "result": {
                            "success": True,
                            "invoice_id": "neo4j-uuid-abc",
                            "invoice_number": "INV-2025-0042",
                            "amount": 48500.0,
                            "line_items_count": 3,
                            "validation_anomalies": [],
                            "status": "success",
                        },
                        "status": "success",
                    }
                ],
                "status": "success",
                "metadata": {
                    "execution_mode": "upload",
                    "execution_time": 0.8,
                    "steps_completed": 1,
                    "steps_total": 1,
                    "tools_used": ["InvoiceUploadTool"],
                },
            }

            mock_openai_client["planner"].extract_json.return_value = {
                "route": "upload_plan",
                "execution_mode": None,
                "reasoning": "User uploaded an invoice PDF",
                "plan": {
                    "intent": "Process invoice PDF upload",
                    "steps": [
                        {
                            "tool": "InvoiceUploadTool",
                            "action": "Process invoice /tmp/invoice.pdf",
                        }
                    ],
                },
            }

            mock_openai_client["validator"].extract_json.return_value = {
                "overall_valid": True,
                "answers_question": True,
                "is_coherent": True,
                "has_errors": False,
                "has_sufficient_data": True,
                "issues": [],
            }

            mock_openai_client["responder"].extract_json.return_value = {
                "response": "Invoice **INV-2025-0042** processed successfully for **$48,500**.",
                "display_format": "text",
                "data": {"summary": "Invoice ingested"},
            }

            graph = create_multi_agent_graph()
            initial_state = {
                "user_query": "Upload this invoice",
                "conversation_history": [],
                "retry_count": 0,
                "user_id": "user-upload-test",
            }

            final_state = invoke_graph(graph, initial_state)

            assert final_state["route"] == "upload_plan"
            assert final_state["execution_mode"] == "upload"
            assert final_state["execution_results"]["status"] == "success"
            assert "INV-2025-0042" in final_state["final_response"]
            assert mock_upload.execute.called

    def test_upload_user_id_forwarded_to_agent(self, mock_openai_client):
        """Test that user_id from state is forwarded to UploadAgent.execute."""
        with patch("backend.agents.orchestrator.UploadAgent") as mock_upload_cls:
            mock_upload = Mock()
            mock_upload_cls.return_value = mock_upload
            mock_upload.execute.return_value = {
                "results": [
                    {
                        "step": 1,
                        "tool": "InvoiceUploadTool",
                        "action": "Upload",
                        "result": {"success": True, "status": "success"},
                        "status": "success",
                    }
                ],
                "status": "success",
                "metadata": {
                    "execution_mode": "upload",
                    "execution_time": 0.5,
                    "steps_completed": 1,
                    "steps_total": 1,
                    "tools_used": ["InvoiceUploadTool"],
                },
            }

            mock_openai_client["planner"].extract_json.return_value = {
                "route": "upload_plan",
                "reasoning": "Upload document",
                "plan": {
                    "intent": "Upload document",
                    "steps": [{"tool": "InvoiceUploadTool", "action": "Upload"}],
                },
            }

            mock_openai_client["validator"].extract_json.return_value = {
                "overall_valid": True,
                "answers_question": True,
                "is_coherent": True,
                "has_errors": False,
                "has_sufficient_data": True,
                "issues": [],
            }

            mock_openai_client["responder"].extract_json.return_value = {
                "response": "Upload confirmed.",
                "display_format": "text",
                "data": {},
            }

            graph = create_multi_agent_graph()
            initial_state = {
                "user_query": "Upload document",
                "conversation_history": [],
                "retry_count": 0,
                "user_id": "owner-9999",
            }

            invoke_graph(graph, initial_state)

            call_kw = mock_upload.execute.call_args.kwargs
            assert call_kw.get("user_id") == "owner-9999"


class TestUserIdPropagation:
    """Test that user_id from state flows to executor tool calls."""

    def test_user_id_passed_to_executor_tool(self, mock_openai_client, mock_tools):
        """Test that user_id in initial_state reaches tool.run() kwargs."""
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Simple date query",
            "plan": {
                "intent": "Get current date",
                "one_way": {
                    "steps": [{"tool": "DateTimeTool", "action": "Get current date"}]
                },
            },
        }

        mock_tools["datetime"].run.return_value = {
            "result": "2025-03-01",
            "status": "success",
        }

        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": True,
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "issues": [],
        }

        mock_openai_client["responder"].extract_json.return_value = {
            "response": "Today is March 1st, 2025.",
            "display_format": "text",
            "data": {},
        }

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": "What is today's date?",
            "conversation_history": [],
            "retry_count": 0,
            "user_id": "isolated-user-xyz",
        }

        invoke_graph(graph, initial_state)

        assert mock_tools["datetime"].run.called
        call_kw = mock_tools["datetime"].run.call_args.kwargs
        assert call_kw.get("user_id") == "isolated-user-xyz"

    def test_default_user_id_when_absent(self, mock_openai_client, mock_tools):
        """Test that 'default_user' is used when user_id is not in state."""
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Date query",
            "plan": {
                "intent": "Get date",
                "one_way": {
                    "steps": [{"tool": "DateTimeTool", "action": "Get current date"}]
                },
            },
        }

        mock_tools["datetime"].run.return_value = {"result": "2025-03-01", "status": "success"}

        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": True,
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "issues": [],
        }

        mock_openai_client["responder"].extract_json.return_value = {
            "response": "Today is March 1st, 2025.",
            "display_format": "text",
            "data": {},
        }

        graph = create_multi_agent_graph()
        # No user_id in state
        initial_state = {
            "user_query": "What is today's date?",
            "conversation_history": [],
            "retry_count": 0,
        }

        invoke_graph(graph, initial_state)

        call_kw = mock_tools["datetime"].run.call_args.kwargs
        assert call_kw.get("user_id") == "default_user"


class TestToolFailureHandling:
    """Test that tool exceptions are caught and graph completes gracefully."""

    def test_tool_exception_does_not_crash_graph(self, mock_openai_client, mock_tools):
        """
        Test that a tool raising an exception results in a graceful error response.

        Flow: executor catches exception → validator marks invalid → retry loop (×2) →
              responder.format_error_response() (no LLM call) → final_response set.
        """
        # Both initial analyze() and retry_with_feedback() use extract_json
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Query invoices",
            "plan": {
                "intent": "Find invoices",
                "one_way": {
                    "steps": [{"tool": "CypherQueryTool", "action": "MATCH (i:Invoice) RETURN i"}]
                },
            },
        }

        # Tool raises on every call (including retries)
        mock_tools["cypher"].run.side_effect = Exception("Neo4j connection refused")

        # Validator always marks invalid (all steps failed)
        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": False,
            "answers_question": False,
            "is_coherent": False,
            "has_errors": True,
            "has_sufficient_data": False,
            "issues": ["Tool execution failed: Neo4j connection refused"],
            "retry_suggestion": "Check database connectivity and retry",
        }

        # Note: format_error_response() does NOT call the LLM —
        # it constructs the message directly from issues/retry_suggestion.
        # No need to mock responder.extract_json for this path.

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": "Show me all invoices",
            "conversation_history": [],
            "retry_count": 0,
        }

        # Must not raise
        final_state = invoke_graph(graph, initial_state)

        assert "final_response" in final_state
        assert len(final_state["final_response"]) > 0
        # Retry loop ran to completion (planner increments on each retry call)
        assert final_state["retry_count"] == 2
        # format_error_response begins with "I tried multiple approaches..."
        assert "tried" in final_state["final_response"].lower()

    def test_partial_tool_failure_still_validates(self, mock_openai_client, mock_tools):
        """
        Test that partial tool failure (one succeeds, one fails) goes to validator
        and succeeds if the good result answers the question.
        """
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Query and calculate",
            "plan": {
                "intent": "Find invoices and sum",
                "one_way": {
                    "steps": [
                        {"tool": "CypherQueryTool", "action": "Find invoices"},
                        {"tool": "CalculatorTool", "action": "Sum amounts"},
                    ]
                },
            },
        }

        # First tool succeeds, second fails
        mock_tools["cypher"].run.return_value = {
            "results": [{"invoice_number": "INV-001", "amount": 10000}],
            "count": 1,
            "status": "success",
        }
        mock_tools["calculator"].run.side_effect = Exception("Division by zero")

        # Validator accepts the partial result
        mock_openai_client["validator"].extract_json.return_value = {
            "overall_valid": True,
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "issues": [],
        }

        mock_openai_client["responder"].extract_json.return_value = {
            "response": "Found **1 invoice**: INV-001 for $10,000.",
            "display_format": "text",
            "data": {},
        }

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": "Show me invoices and their total",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        assert final_state["execution_results"]["status"] == "partial"
        assert final_state["validation_result"]["valid"] is True
        assert "INV-001" in final_state["final_response"]


class TestRoutingFunctions:
    """Unit tests for routing functions — no graph execution needed."""

    def test_route_after_planner_generic(self):
        """generic_response → responder (fast path)."""
        from backend.agents.orchestrator import route_after_planner
        state = {"route": "generic_response"}
        assert route_after_planner(state) == "responder"

    def test_route_after_planner_clarification(self):
        """clarification → responder (fast path)."""
        from backend.agents.orchestrator import route_after_planner
        state = {"route": "clarification"}
        assert route_after_planner(state) == "responder"

    def test_route_after_planner_execution(self):
        """execution_plan → executor."""
        from backend.agents.orchestrator import route_after_planner
        state = {"route": "execution_plan", "execution_mode": "one_way"}
        assert route_after_planner(state) == "executor"

    def test_route_after_planner_upload(self):
        """upload_plan → upload_agent."""
        from backend.agents.orchestrator import route_after_planner
        state = {"route": "upload_plan"}
        assert route_after_planner(state) == "upload_agent"

    def test_route_after_executor_one_way(self):
        """one_way always goes to validator."""
        from backend.agents.orchestrator import route_after_executor
        state = {"execution_mode": "one_way"}
        assert route_after_executor(state) == "validator"

    def test_route_after_executor_react_continues(self):
        """react with steps remaining goes to planner_react."""
        from backend.agents.orchestrator import route_after_executor
        state = {"execution_mode": "react", "current_step": 2, "react_max_steps": 5}
        assert route_after_executor(state) == "planner_react"

    def test_route_after_executor_react_max_steps_reached(self):
        """react at max steps goes directly to validator without another planner call."""
        from backend.agents.orchestrator import route_after_executor
        state = {"execution_mode": "react", "current_step": 5, "react_max_steps": 5}
        assert route_after_executor(state) == "validator"

    def test_route_after_planner_react_continue(self):
        """react_continue=True → executor."""
        from backend.agents.orchestrator import route_after_planner_react
        state = {"react_continue": True}
        assert route_after_planner_react(state) == "executor"

    def test_route_after_planner_react_done(self):
        """react_continue=False → validator."""
        from backend.agents.orchestrator import route_after_planner_react
        state = {"react_continue": False}
        assert route_after_planner_react(state) == "validator"

    def test_route_after_validator_valid(self):
        """Valid result → responder."""
        from backend.agents.orchestrator import route_after_validator
        state = {"validation_result": {"valid": True}, "retry_count": 0}
        assert route_after_validator(state) == "responder"

    def test_route_after_validator_retry(self):
        """Invalid result under retry limit → planner."""
        from backend.agents.orchestrator import route_after_validator
        state = {"validation_result": {"valid": False}, "retry_count": 1}
        assert route_after_validator(state) == "planner"

    def test_route_after_validator_max_retries(self):
        """Invalid result at retry limit → responder (error path)."""
        from backend.agents.orchestrator import route_after_validator
        state = {"validation_result": {"valid": False}, "retry_count": 2}
        assert route_after_validator(state) == "responder"


class TestLongTermMemories:
    """Test that long_term_memories from state reaches the planner prompt."""

    def test_memories_passed_to_planner_prompt(self, mock_openai_client):
        """Verify long_term_memories is forwarded into the planner's LLM prompt."""
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "generic_response",
            "execution_mode": None,
            "reasoning": "Greeting",
            "response": "Hello!",
        }

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": "What are my outstanding invoices?",
            "conversation_history": [],
            "retry_count": 0,
            "long_term_memories": "User currency preference is USD. Last project queried: PRJ-042.",
        }

        invoke_graph(graph, initial_state)

        # Planner's extract_json receives the rendered prompt as first positional arg
        planner_call = mock_openai_client["planner"].extract_json.call_args
        assert planner_call is not None
        rendered_prompt = planner_call[0][0]  # First positional arg
        assert "USD" in rendered_prompt
        assert "PRJ-042" in rendered_prompt

    def test_missing_memories_does_not_crash(self, mock_openai_client):
        """Workflow completes normally when long_term_memories is absent from state."""
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "generic_response",
            "execution_mode": None,
            "reasoning": "Greeting",
            "response": "Hello!",
        }

        graph = create_multi_agent_graph()
        # No long_term_memories key in state
        initial_state = {
            "user_query": "Hello",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)
        assert "final_response" in final_state


class TestUnknownTool:
    """Test executor gracefully handles plan steps that name non-existent tools."""

    def test_unknown_tool_name_handled_gracefully(self, mock_openai_client, mock_tools):
        """
        When Planner returns a step with an unknown tool name, executor records
        it as failed. Validator early-exits (all tools failed), retry loop runs
        to max, then responder returns a user-friendly error — graph does not crash.
        """
        # Planner always returns a plan with a non-existent tool
        mock_openai_client["planner"].extract_json.return_value = {
            "route": "execution_plan",
            "execution_mode": "one_way",
            "reasoning": "Run unknown tool",
            "plan": {
                "intent": "Do something",
                "one_way": {
                    "steps": [{"tool": "NonExistentTool", "action": "Do something"}]
                },
            },
        }

        # Validator and responder are NOT called via LLM in this path:
        # - Validator early-exits (all tools failed) without calling its LLM
        # - Responder uses format_error_response() which is hardcoded (no LLM)
        # No extract_json mock needed for them here.

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": "Do something impossible",
            "conversation_history": [],
            "retry_count": 0,
        }

        final_state = invoke_graph(graph, initial_state)

        # Graph completed without raising
        assert "final_response" in final_state
        assert len(final_state["final_response"]) > 0
        # Retry loop exhausted
        assert final_state["retry_count"] == 2
        # Error response message
        assert "tried" in final_state["final_response"].lower()
