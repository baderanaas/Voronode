"""
Validator Agent - Quality assurance for responses.

Validates response quality before sending to user. Catches hallucinations, errors,
and incomplete results. Provides feedback to Planner for retry loop.
"""

import structlog
from typing import Dict, Any

from backend.services.llm_client import OpenAIClient

logger = structlog.get_logger()


class ValidatorAgent:
    """
    Agent that validates response quality before returning to user.

    Responsibilities:
    1. Check results not empty
    2. Verify all tools succeeded
    3. Validate response answers the question (LLM check)
    4. Check for hallucinations and errors
    5. Provide feedback for retry loop
    """

    def __init__(self):
        """Initialize Validator with OpenAI LLM client (GPT-4o-mini)."""
        self.llm = OpenAIClient()

    def validate(
        self,
        user_query: str,
        execution_results: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate response quality.

        Performs multiple validation checks:
        1. Results not empty?
        2. All tools succeeded?
        3. Response coherent and relevant?
        4. Answers the original question?
        5. No hallucinations (data grounded in results)?

        Args:
            user_query: Original user query
            execution_results: Results from Executor
            plan: Execution plan from Planner (for expected outcome)

        Returns:
            {
                "valid": true/false,
                "issues": ["issue1", "issue2"],  # If invalid
                "retry_suggestion": "<how to fix>",  # If invalid
                "metadata": {...}  # Execution metadata
            }
        """
        logger.info("validator_checking_quality", query=user_query[:100])

        # Check 1: Results exist
        if not execution_results.get("results"):
            logger.warning("validator_no_results")
            return {
                "valid": False,
                "issues": ["No results returned from tool execution"],
                "retry_suggestion": "Rephrase query or check if data exists in the system",
            }

        # Check 2: All tools succeeded (or at least some succeeded)
        results = execution_results.get("results", [])
        failed_tools = [
            r for r in results
            if r.get("status") == "failed"
        ]

        # If ALL tools failed, that's a problem
        if failed_tools and len(failed_tools) == len(results):
            logger.warning("validator_all_tools_failed", failed_count=len(failed_tools))
            return {
                "valid": False,
                "issues": [f"All tools failed: {[t.get('tool') for t in failed_tools]}"],
                "retry_suggestion": "Try different tools or parameters. Check if data exists.",
            }

        # If SOME tools failed, include as partial issue but continue validation
        partial_failure = len(failed_tools) > 0

        # Check 3: LLM validation - does response answer the question?
        validation_result = self._llm_validate(
            user_query=user_query,
            execution_results=results,
            plan_intent=plan.get("intent", "unknown"),
            partial_failure=partial_failure,
        )

        if not validation_result["overall_valid"]:
            logger.warning("validator_llm_check_failed", issues=validation_result.get("issues"))
            return {
                "valid": False,
                "issues": validation_result["issues"],
                "retry_suggestion": validation_result.get("retry_suggestion", "Try a different approach"),
            }

        # All checks passed!
        logger.info("validator_passed")
        return {
            "valid": True,
            "metadata": execution_results.get("metadata", {}),
        }

    def _llm_validate(
        self,
        user_query: str,
        execution_results: list,
        plan_intent: str,
        partial_failure: bool,
    ) -> Dict[str, Any]:
        """
        Use LLM to validate response quality.

        Args:
            user_query: Original user query
            execution_results: Tool execution results
            plan_intent: Expected intent from plan
            partial_failure: Whether some tools failed

        Returns:
            {
                "overall_valid": true/false,
                "answers_question": true/false,
                "is_coherent": true/false,
                "has_errors": true/false,
                "issues": [...],
                "retry_suggestion": "..."
            }
        """
        # Extract successful results for validation
        successful_results = [
            r for r in execution_results
            if r.get("status") == "success"
        ]

        prompt = f"""
        Validate the quality of these tool execution results.

        Original Question: "{user_query}"
        Expected Intent: "{plan_intent}"
        Execution Results: {successful_results}
        Partial Tool Failures: {partial_failure}

        Validation Questions:
        1. Do the successful results contain enough information to answer the original question?
        2. Is the data coherent and relevant to the query?
        3. Are there any obvious errors or inconsistencies in the results?
        4. If there were partial failures, do the successful results still provide value?
        5. Is there any indication of hallucination (making up data not in results)?

        Guidelines:
        - Be strict but fair
        - Consider partial failures: if some tools succeeded with useful data, that may be okay
        - Check if results actually answer the question (not just return data)
        - Look for empty datasets that should have data
        - Check for logical inconsistencies

        Respond in JSON:
        {{
            "answers_question": true/false,
            "is_coherent": true/false,
            "has_errors": true/false,
            "has_sufficient_data": true/false,
            "overall_valid": true/false,
            "issues": ["<list of specific issues>"],
            "retry_suggestion": "<concrete suggestion for how to fix>"
        }}
        """

        logger.info("validator_llm_checking")
        result = self.llm.extract_json(prompt, temperature=0.1)

        logger.info(
            "validator_llm_result",
            valid=result.get("overall_valid"),
            issues_count=len(result.get("issues", [])),
        )

        return result
