"""
Planner Agent - Entry point for multi-agent system.

Analyzes user queries, classifies intent, selects execution mode (one_way vs react),
and creates execution plans. Also handles retry logic when validation fails.
"""

import structlog
from typing import Dict, Any, List

from backend.services.llm_client import GeminiClient
from backend.agents.prompts.prompt_manager import render_prompt

logger = structlog.get_logger()


class PlannerAgent:
    """
    Entry agent that analyzes queries and creates execution plans.

    Responsibilities:
    1. Classify user intent (generic_response vs execution_plan vs clarification)
    2. Select execution mode (one_way for simple, react for complex)
    3. Create initial execution plan
    4. Reformulate plan on validation failure (retry loop)
    5. Plan next step in ReAct mode based on previous results
    """

    def __init__(self):
        """Initialize Planner with Gemini LLM client (Gemini 2.5 Pro for complex planning)."""
        self.llm = GeminiClient()

    def analyze(self, user_message: str, history: List[Dict[str, str]], memories: str = "") -> Dict[str, Any]:
        """
        Analyze user query and decide routing + execution mode.

        Args:
            user_message: Current user query
            history: Conversation history (last 5 turns)

        Returns:
            {
                "route": "generic_response" | "execution_plan" | "clarification",
                "execution_mode": "one_way" | "react",  # Only if execution_plan
                "reasoning": "<why this route and mode>",
                "response": "<text>",  # If generic_response or clarification
                "plan": {  # Only if execution_plan
                    "intent": "<what user wants>",
                    "one_way": {...} or "react": {...}
                }
            }
        """
        prompt = render_prompt(
            "planner/analyze.j2",
            user_message=user_message,
            history=history,
            memories=memories,
        )

        logger.info("planner_analyzing_query", query=user_message[:100])
        result = self.llm.extract_json(prompt, temperature=0.2)

        logger.info(
            "planner_decision",
            route=result.get("route"),
            execution_mode=result.get("execution_mode"),
        )

        return result

    def retry_with_feedback(
        self,
        user_query: str,
        previous_plan: Dict[str, Any],
        validation_feedback: Dict[str, Any],
        retry_count: int,
    ) -> Dict[str, Any]:
        """
        Reformulate plan based on Validator feedback.

        Called when validation fails. Creates a new execution plan that addresses
        the issues identified by the Validator.

        Args:
            user_query: Original user query
            previous_plan: The plan that failed validation
            validation_feedback: Issues and suggestions from Validator
            retry_count: Number of retries so far (0-indexed)

        Returns:
            New execution plan with alternative approach
        """
        prompt = render_prompt(
            "planner/retry_with_feedback.j2",
            user_query=user_query,
            previous_plan=previous_plan,
            issues=validation_feedback.get('issues', []),
            retry_suggestion=validation_feedback.get('retry_suggestion', 'Try a different approach'),
            retry_count=retry_count,
        )

        logger.info("planner_retrying_with_feedback", retry_count=retry_count)
        result = self.llm.extract_json(prompt, temperature=0.3)

        logger.info(
            "planner_retry_decision",
            route=result.get("route"),
            retry_count=retry_count,
        )

        return result

    def plan_next_step(
        self,
        user_query: str,
        completed_steps: List[Dict[str, Any]],
        current_results: Dict[str, Any],
        strategy: str,
    ) -> Dict[str, Any]:
        """
        Plan next step in ReAct loop based on previous results.

        Called in ReAct mode after each step execution to decide whether to
        continue or finish.

        Args:
            user_query: Original user query
            completed_steps: List of completed steps with results
            current_results: Results from the most recent step
            strategy: High-level strategy from initial plan

        Returns:
            {
                "continue": true/false,
                "reasoning": "<explanation>",
                "next_step": {  // If continue=true
                    "tool": "<tool_name>",
                    "action": "<what to do>",
                    "depends_on": "<previous step>"
                }
            }
        """
        prompt = render_prompt(
            "planner/plan_next_step.j2",
            user_query=user_query,
            strategy=strategy,
            completed_steps=completed_steps,
            current_results=current_results,
        )

        logger.info("planner_react_planning_next_step", completed_steps=len(completed_steps))
        result = self.llm.extract_json(prompt, temperature=0.2)

        logger.info(
            "planner_react_decision",
            continue_execution=result.get("continue"),
            step_count=len(completed_steps),
        )

        return result
