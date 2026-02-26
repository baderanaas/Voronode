"""
State definition for Multi-Agent Conversational System.

Defines ConversationState TypedDict used across all agents and LangGraph workflow.
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any


class ConversationState(TypedDict, total=False):
    """
    State for hybrid multi-agent conversational system.

    This state is passed between all agents in the LangGraph workflow and tracks
    the complete conversation context, execution plan, results, and validation.
    """

    # ===== User Identity =====
    user_id: str
    """User identifier for data scoping. Defaults to 'default_user' until auth is added."""

    # ===== User Input =====
    user_query: str
    """The current user query/message."""

    long_term_memories: str
    """Relevant facts retrieved from Mem0 (cross-session semantic memory). Empty string if none."""

    conversation_history: List[Dict[str, str]]
    """
    Previous conversation turns for context.
    Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """

    # ===== Planner Outputs =====
    route: Literal["generic_response", "execution_plan", "clarification"]
    """
    Routing decision from Planner:
    - generic_response: Static response (greetings, help, out-of-scope, etc.)
    - execution_plan: Data query requiring tool execution
    - clarification: Ambiguous query, need more info from user
    """

    execution_mode: Literal["one_way", "react"]
    """
    Execution strategy for data queries:
    - one_way: Execute all steps at once (simple queries)
    - react: Iterative planning and execution (complex queries)
    """

    planner_output: Dict[str, Any]
    """
    Full output from Planner including route, plan, and reasoning.
    Contains execution plan with tools and steps.
    """

    # ===== Executor Outputs =====
    execution_results: Dict[str, Any]
    """
    Results from tool execution including data and metadata.
    Contains tool outputs, execution time, status, etc.
    """

    # ===== ReAct-Specific State =====
    current_step: int
    """Current step number in ReAct execution (0-indexed)."""

    completed_steps: List[Dict[str, Any]]
    """
    History of completed steps in ReAct mode.
    Each entry contains tool name, action, result, and status.
    """

    react_continue: bool
    """
    Whether to continue ReAct loop (decided by planner_react_node).
    True = execute next step, False = move to validation.
    """

    react_max_steps: int
    """Maximum steps allowed in ReAct mode to prevent infinite loops (default: 5)."""

    next_step: Dict[str, Any]
    """
    Next step to execute in ReAct mode (from planner_react_node).
    Contains tool name and action for the next iteration.
    """

    # ===== Validator Outputs =====
    validation_result: Dict[str, Any]
    """
    Validation result from ValidatorAgent.
    Contains: valid (bool), issues (list), retry_suggestion (str), response (str if valid).
    """

    validation_feedback: Optional[Dict[str, Any]]
    """
    Feedback from Validator to Planner for retry loop.
    Contains: issues, retry_suggestion, previous_results.
    Only populated when validation fails.
    """

    # ===== Responder Outputs =====
    display_format: str
    """
    Display format for final response:
    - "text": Simple text response
    - "table": Tabular data
    - "chart": Chart/visualization
    """

    display_data: Optional[Dict[str, Any]]
    """
    Structured data for visualization (from Responder).
    Contains rows, summary, metadata for tables/charts.
    """

    # ===== Control Flow =====
    retry_count: int
    """
    Number of retry attempts for validation failures (max 2).
    Used to prevent infinite retry loops.
    """

    final_response: str
    """
    Final formatted response text for user.
    Set by ResponderAgent as the last step before END.
    """


# Type aliases for cleaner code
RouteType = Literal["generic_response", "execution_plan", "clarification"]
ExecutionMode = Literal["one_way", "react"]
DisplayFormat = Literal["text", "table", "chart"]
