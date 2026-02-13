"""
Unit tests for ValidatorAgent.

Tests:
- validate() with successful results
- validate() with empty results
- validate() with all tools failed
- validate() with partial tool failures
- _llm_validate() quality checks
"""

import pytest
from unittest.mock import Mock, patch

from backend.agents.multi_agent.validator_agent import ValidatorAgent


@pytest.fixture
def validator_agent():
    """Create ValidatorAgent with mocked OpenAIClient."""
    with patch("backend.agents.multi_agent.validator_agent.OpenAIClient") as mock_openai_cls:
        mock_openai = Mock()
        mock_openai_cls.return_value = mock_openai
        agent = ValidatorAgent()
        agent.llm = mock_openai
        yield agent


@pytest.fixture
def successful_execution_results():
    """Execution results with all tools successful."""
    return {
        "results": [
            {
                "step": 1,
                "tool": "CypherQueryTool",
                "status": "success",
                "result": {"cypher_query": "MATCH ...", "results": [{"invoice": "INV-001"}], "count": 1},
            },
            {
                "step": 2,
                "tool": "CalculatorTool",
                "status": "success",
                "result": {"operation": "sum", "result": 125000},
            },
        ],
        "metadata": {"execution_time": 1.5, "tools_used": ["CypherQueryTool", "CalculatorTool"]},
    }


@pytest.fixture
def valid_plan():
    """Valid execution plan."""
    return {
        "intent": "Show invoices over $50k",
        "one_way": {
            "steps": [
                {"tool": "CypherQueryTool", "action": "Find invoices > $50000"},
                {"tool": "CalculatorTool", "action": "Sum amounts"},
            ]
        },
    }


class TestValidate:
    """Test validation logic."""

    def test_validate_successful_results(self, validator_agent, successful_execution_results, valid_plan):
        """Test validation passes with successful results."""
        # Mock LLM validation to pass
        validator_agent.llm.extract_json.return_value = {
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "overall_valid": True,
            "issues": [],
            "retry_suggestion": "",
        }

        result = validator_agent.validate(
            user_query="Show me invoices over $50k",
            execution_results=successful_execution_results,
            plan=valid_plan,
        )

        assert result["valid"] is True
        assert "metadata" in result
        validator_agent.llm.extract_json.assert_called_once()

    def test_validate_empty_results(self, validator_agent, valid_plan):
        """Test validation fails with no results."""
        empty_results = {"results": [], "metadata": {}}

        result = validator_agent.validate(
            user_query="Show me invoices",
            execution_results=empty_results,
            plan=valid_plan,
        )

        assert result["valid"] is False
        assert "issues" in result
        assert "No results" in result["issues"][0]
        assert "retry_suggestion" in result

        # LLM should not be called for empty results check
        validator_agent.llm.extract_json.assert_not_called()

    def test_validate_all_tools_failed(self, validator_agent, valid_plan):
        """Test validation fails when all tools fail."""
        failed_results = {
            "results": [
                {
                    "step": 1,
                    "tool": "CypherQueryTool",
                    "status": "failed",
                    "error": "Connection error",
                },
                {
                    "step": 2,
                    "tool": "CalculatorTool",
                    "status": "failed",
                    "error": "Invalid data",
                },
            ],
            "metadata": {},
        }

        result = validator_agent.validate(
            user_query="Show me data",
            execution_results=failed_results,
            plan=valid_plan,
        )

        assert result["valid"] is False
        assert "issues" in result
        assert "All tools failed" in result["issues"][0]
        assert "retry_suggestion" in result

    def test_validate_partial_failures(self, validator_agent, valid_plan):
        """Test validation with some tools failed but some succeeded."""
        partial_results = {
            "results": [
                {
                    "step": 1,
                    "tool": "CypherQueryTool",
                    "status": "success",
                    "result": {"results": [{"invoice": "INV-001"}]},
                },
                {
                    "step": 2,
                    "tool": "CalculatorTool",
                    "status": "failed",
                    "error": "Division by zero",
                },
            ],
            "metadata": {},
        }

        # Mock LLM to accept partial results
        validator_agent.llm.extract_json.return_value = {
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "overall_valid": True,
            "issues": [],
            "retry_suggestion": "",
        }

        result = validator_agent.validate(
            user_query="Show me invoices",
            execution_results=partial_results,
            plan=valid_plan,
        )

        # Should pass if LLM says successful results are sufficient
        assert result["valid"] is True

        # Verify LLM was told about partial failure
        call_args = validator_agent.llm.extract_json.call_args
        assert call_args is not None

    def test_validate_llm_rejects(self, validator_agent, successful_execution_results, valid_plan):
        """Test validation fails when LLM rejects quality."""
        # Mock LLM to reject
        validator_agent.llm.extract_json.return_value = {
            "answers_question": False,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": False,
            "overall_valid": False,
            "issues": ["Results don't answer the question", "Missing key information"],
            "retry_suggestion": "Query different data or add filtering",
        }

        result = validator_agent.validate(
            user_query="Show me invoices over $50k",
            execution_results=successful_execution_results,
            plan=valid_plan,
        )

        assert result["valid"] is False
        assert len(result["issues"]) == 2
        assert "retry_suggestion" in result
        assert "different data" in result["retry_suggestion"]


class TestLLMValidate:
    """Test LLM-based quality validation."""

    def test_llm_validate_passes(self, validator_agent):
        """Test LLM validation passes for good results."""
        execution_results = [
            {
                "tool": "CypherQueryTool",
                "status": "success",
                "result": {"results": [{"invoice_number": "INV-001", "amount": 75000}], "count": 1},
            }
        ]

        validator_agent.llm.extract_json.return_value = {
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "overall_valid": True,
            "issues": [],
            "retry_suggestion": "",
        }

        result = validator_agent._llm_validate(
            user_query="Show me invoices over $50k",
            execution_results=execution_results,
            plan_intent="Find high-value invoices",
            partial_failure=False,
        )

        assert result["overall_valid"] is True
        assert result["answers_question"] is True
        assert result["is_coherent"] is True
        assert result["has_errors"] is False
        assert len(result["issues"]) == 0

    def test_llm_validate_fails(self, validator_agent):
        """Test LLM validation fails for poor results."""
        execution_results = [
            {
                "tool": "CypherQueryTool",
                "status": "success",
                "result": {"results": [], "count": 0},  # Empty results
            }
        ]

        validator_agent.llm.extract_json.return_value = {
            "answers_question": False,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": False,
            "overall_valid": False,
            "issues": ["Query returned no results when data should exist"],
            "retry_suggestion": "Check query parameters or try broader search",
        }

        result = validator_agent._llm_validate(
            user_query="Show me all invoices",
            execution_results=execution_results,
            plan_intent="Find all invoices",
            partial_failure=False,
        )

        assert result["overall_valid"] is False
        assert result["has_sufficient_data"] is False
        assert len(result["issues"]) > 0

    def test_llm_validate_with_partial_failure(self, validator_agent):
        """Test LLM validation considers partial failures."""
        execution_results = [
            {"tool": "CypherQueryTool", "status": "success", "result": {"results": [{"data": "value"}]}},
        ]

        validator_agent.llm.extract_json.return_value = {
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "overall_valid": True,
            "issues": [],
            "retry_suggestion": "",
        }

        result = validator_agent._llm_validate(
            user_query="Get data",
            execution_results=execution_results,
            plan_intent="Retrieve data",
            partial_failure=True,  # Some tools failed
        )

        # Should still validate successful results
        assert result["overall_valid"] is True

        # Verify LLM was informed about partial failure
        call_args = validator_agent.llm.extract_json.call_args
        prompt = str(call_args)
        assert "partial" in prompt.lower() or "failure" in prompt.lower()

    def test_llm_validate_temperature(self, validator_agent):
        """Test that LLM validation uses low temperature for consistency."""
        execution_results = [{"tool": "CypherQueryTool", "status": "success", "result": {}}]

        validator_agent.llm.extract_json.return_value = {
            "overall_valid": True,
            "answers_question": True,
            "is_coherent": True,
            "has_errors": False,
            "has_sufficient_data": True,
            "issues": [],
        }

        validator_agent._llm_validate(
            user_query="test",
            execution_results=execution_results,
            plan_intent="test",
            partial_failure=False,
        )

        # Verify temperature is 0.1 (strict)
        call_kwargs = validator_agent.llm.extract_json.call_args.kwargs
        assert call_kwargs["temperature"] == 0.1
