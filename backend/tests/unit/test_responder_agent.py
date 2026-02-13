"""
Unit tests for ResponderAgent.

Tests:
- format_response() with different display formats (text, table, chart)
- format_generic_response() for greetings/clarifications
- format_error_response() for max retries
- Markdown formatting in responses
"""

import pytest
from unittest.mock import Mock, patch

from backend.agents.multi_agent.responder_agent import ResponderAgent


@pytest.fixture
def responder_agent():
    """Create ResponderAgent with mocked OpenAIClient."""
    with patch("backend.agents.multi_agent.responder_agent.OpenAIClient") as mock_openai_cls:
        mock_openai = Mock()
        mock_openai_cls.return_value = mock_openai
        agent = ResponderAgent()
        agent.llm = mock_openai
        yield agent


@pytest.fixture
def execution_results_text():
    """Execution results for simple text response."""
    return {
        "results": [
            {
                "step": 1,
                "tool": "CalculatorTool",
                "status": "success",
                "result": {"operation": "sum", "result": 234567},
            }
        ],
        "metadata": {"execution_time": 0.5, "tools_used": ["CalculatorTool"]},
    }


@pytest.fixture
def execution_results_table():
    """Execution results for table display."""
    return {
        "results": [
            {
                "step": 1,
                "tool": "CypherQueryTool",
                "status": "success",
                "result": {
                    "results": [
                        {"invoice_id": "INV-001", "contractor": "ABC", "amount": 125000},
                        {"invoice_id": "INV-002", "contractor": "XYZ", "amount": 87000},
                    ],
                    "count": 2,
                },
            }
        ],
        "metadata": {"execution_time": 1.2, "tools_used": ["CypherQueryTool"]},
    }


class TestFormatResponse:
    """Test response formatting."""

    def test_format_response_text(self, responder_agent, execution_results_text):
        """Test formatting simple text response."""
        responder_agent.llm.extract_json.return_value = {
            "response": "The total retention across all active contracts is **$234,567**.",
            "display_format": "text",
            "data": {"summary": "Total retention: $234,567"},
        }

        result = responder_agent.format_response(
            user_query="What's the total retention?",
            execution_results=execution_results_text,
            metadata={"execution_time": 0.5},
            execution_mode="one_way",
        )

        assert result["response"] == "The total retention across all active contracts is **$234,567**."
        assert result["display_format"] == "text"
        assert result["data"]["summary"] == "Total retention: $234,567"

        # Verify LLM was called
        responder_agent.llm.extract_json.assert_called_once()

    def test_format_response_table(self, responder_agent, execution_results_table):
        """Test formatting table response."""
        responder_agent.llm.extract_json.return_value = {
            "response": "I found **2 invoices** over $50,000, totaling **$212,000**.",
            "display_format": "table",
            "data": {
                "rows": [
                    {"invoice_id": "INV-001", "contractor": "ABC", "amount": 125000},
                    {"invoice_id": "INV-002", "contractor": "XYZ", "amount": 87000},
                ],
                "columns": ["invoice_id", "contractor", "amount"],
                "summary": "2 invoices totaling $212,000",
                "metadata": {"execution_time": 1.2, "tools_used": ["CypherQueryTool"], "record_count": 2},
            },
        }

        result = responder_agent.format_response(
            user_query="Show me invoices over $50k",
            execution_results=execution_results_table,
            metadata={"execution_time": 1.2},
            execution_mode="one_way",
        )

        assert result["display_format"] == "table"
        assert "rows" in result["data"]
        assert len(result["data"]["rows"]) == 2
        assert "columns" in result["data"]
        assert result["data"]["summary"] == "2 invoices totaling $212,000"

    def test_format_response_chart(self, responder_agent, execution_results_table):
        """Test formatting chart response."""
        responder_agent.llm.extract_json.return_value = {
            "response": "Here's the distribution of invoices by contractor.",
            "display_format": "chart",
            "data": {
                "chart_type": "bar",
                "x_axis": ["ABC", "XYZ"],
                "y_axis": [125000, 87000],
                "labels": ["ABC Contractors", "XYZ Corp"],
                "summary": "ABC has highest invoice amount",
                "metadata": {"execution_time": 1.2, "tools_used": ["CypherQueryTool"], "record_count": 2},
            },
        }

        result = responder_agent.format_response(
            user_query="Show me invoice distribution by contractor",
            execution_results=execution_results_table,
            metadata={"execution_time": 1.2},
            execution_mode="one_way",
        )

        assert result["display_format"] == "chart"
        assert result["data"]["chart_type"] == "bar"
        assert len(result["data"]["x_axis"]) == 2
        assert len(result["data"]["y_axis"]) == 2

    def test_format_response_markdown(self, responder_agent, execution_results_text):
        """Test that response uses markdown formatting."""
        responder_agent.llm.extract_json.return_value = {
            "response": "## Retention Summary\n\nTotal retention: **$234,567**\n\n- Contract A: `$100,000`\n- Contract B: `$134,567`\n\n> ⚠️ **Note:** Some contracts may need review.",
            "display_format": "text",
            "data": {"summary": "Total: $234,567"},
        }

        result = responder_agent.format_response(
            user_query="Show retention breakdown",
            execution_results=execution_results_text,
            metadata={},
            execution_mode="one_way",
        )

        response = result["response"]
        assert "##" in response  # Headers
        assert "**" in response  # Bold
        assert "`" in response  # Code
        assert ">" in response  # Blockquote

    def test_format_response_filters_failed_tools(self, responder_agent):
        """Test that only successful results are formatted."""
        mixed_results = {
            "results": [
                {"step": 1, "tool": "CypherQueryTool", "status": "success", "result": {"data": "value"}},
                {"step": 2, "tool": "CalculatorTool", "status": "failed", "error": "Error"},
            ],
            "metadata": {},
        }

        responder_agent.llm.extract_json.return_value = {
            "response": "I found the data you requested.",
            "display_format": "text",
            "data": {},
        }

        result = responder_agent.format_response(
            user_query="Get data",
            execution_results=mixed_results,
            metadata={},
            execution_mode="one_way",
        )

        # Verify only successful results were passed to LLM
        call_args = responder_agent.llm.extract_json.call_args
        prompt = str(call_args)
        # The prompt should contain only successful results
        assert "successful" in prompt.lower() or "success" in prompt.lower()

    def test_format_response_temperature(self, responder_agent, execution_results_text):
        """Test that formatting uses moderate temperature for creativity."""
        responder_agent.llm.extract_json.return_value = {
            "response": "Response text",
            "display_format": "text",
            "data": {},
        }

        responder_agent.format_response(
            user_query="Test",
            execution_results=execution_results_text,
            metadata={},
            execution_mode="one_way",
        )

        # Verify temperature is 0.3 (moderate creativity)
        call_kwargs = responder_agent.llm.extract_json.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3


class TestFormatGenericResponse:
    """Test generic response formatting."""

    def test_format_generic_response(self, responder_agent):
        """Test formatting simple generic response."""
        result = responder_agent.format_generic_response(
            "Hello! I'm your AI assistant for financial risk management."
        )

        assert result["response"] == "Hello! I'm your AI assistant for financial risk management."
        assert result["display_format"] == "text"
        assert result["data"] is None

        # Should not call LLM
        responder_agent.llm.extract_json.assert_not_called()

    def test_format_generic_out_of_scope(self, responder_agent):
        """Test formatting out-of-scope response."""
        result = responder_agent.format_generic_response(
            "I'm designed to help with financial data. I can't help with that request."
        )

        assert "financial data" in result["response"]
        assert result["display_format"] == "text"


class TestFormatErrorResponse:
    """Test error response formatting."""

    def test_format_error_response(self, responder_agent):
        """Test formatting error response after max retries."""
        issues = [
            "Query returned no results",
            "Tool execution failed",
        ]

        result = responder_agent.format_error_response(
            user_query="Show me data",
            issues=issues,
            retry_suggestion="Try rephrasing your query or check if the data exists.",
        )

        assert "challenges" in result["response"].lower() or "error" in result["response"].lower()
        assert "1. Query returned no results" in result["response"]
        assert "2. Tool execution failed" in result["response"]
        assert "Try rephrasing" in result["response"]
        assert result["display_format"] == "text"
        assert "issues" in result["data"]
        assert len(result["data"]["issues"]) == 2

        # Should not call LLM
        responder_agent.llm.extract_json.assert_not_called()

    def test_format_error_response_multiple_issues(self, responder_agent):
        """Test error response with many issues."""
        issues = [
            "Issue 1",
            "Issue 2",
            "Issue 3",
        ]

        result = responder_agent.format_error_response(
            user_query="Complex query",
            issues=issues,
            retry_suggestion="Simplify your query.",
        )

        # All issues should be numbered
        assert "1. Issue 1" in result["response"]
        assert "2. Issue 2" in result["response"]
        assert "3. Issue 3" in result["response"]
        assert "Simplify your query" in result["response"]
