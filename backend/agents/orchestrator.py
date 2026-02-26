"""
Multi-Agent Orchestrator - LangGraph workflow.

Orchestrates the flow between Planner, Executor, Validator, and Responder agents
with conditional routing for hybrid execution (one_way vs react modes).
"""

import structlog
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.state import ConversationState
from backend.agents.planner_agent import PlannerAgent
from backend.agents.executor_agent import ExecutorAgent
from backend.agents.upload_agent import UploadAgent
from backend.agents.validator_agent import ValidatorAgent
from backend.agents.responder_agent import ResponderAgent

logger = structlog.get_logger()


# ===== Agent Node Implementations =====


def planner_node(state: ConversationState) -> ConversationState:
    """
    Planner agent node.

    Handles:
    - Initial query analysis and routing
    - Retry planning based on validation feedback
    """
    planner = PlannerAgent()

    logger.info(
        "planner_node_executing", has_feedback=bool(state.get("validation_feedback"))
    )

    # Check if this is a retry with validation feedback
    if state.get("validation_feedback"):
        # Re-plan based on feedback
        logger.info("planner_retrying", retry_count=state.get("retry_count", 0))

        output = planner.retry_with_feedback(
            user_query=state["user_query"],
            previous_plan=state["planner_output"].get("plan", {}),
            validation_feedback=state["validation_feedback"],
            retry_count=state.get("retry_count", 0),
        )

        # Increment retry count
        state["retry_count"] = state.get("retry_count", 0) + 1

        # Clear validation feedback for next iteration
        state["validation_feedback"] = None

    else:
        # Initial planning
        logger.info("planner_initial", query=state["user_query"][:100])

        output = planner.analyze(
            user_message=state["user_query"],
            history=state.get("conversation_history", []),
        )

        state["retry_count"] = 0

    # Store planner output
    state["planner_output"] = output
    state["route"] = output["route"]

    # If execution_plan, store execution mode
    if output["route"] == "execution_plan":
        state["execution_mode"] = output.get("execution_mode", "one_way")
        state["react_max_steps"] = 5  # Default max steps for ReAct
        state["current_step"] = 0
        state["completed_steps"] = []
    elif output["route"] == "upload_plan":
        state["execution_mode"] = "upload"
        state["current_step"] = 0
        state["completed_steps"] = []

    # Generic responses and clarifications are formatted by responder_node

    logger.info(
        "planner_node_complete",
        route=state["route"],
        execution_mode=state.get("execution_mode"),
    )

    return state


def executor_node(state: ConversationState) -> ConversationState:
    """
    Executor agent node.

    Handles:
    - One-way execution (all steps at once)
    - ReAct step execution (single step)
    """
    executor = ExecutorAgent()

    execution_mode = state.get("execution_mode", "one_way")

    logger.info("executor_node_executing", mode=execution_mode)

    if execution_mode == "one_way":
        # Execute all steps at once
        plan = state["planner_output"].get("plan", {}).get("one_way", {})

        results = executor.execute_one_way(
            plan=plan,
            user_query=state["user_query"],
        )

        state["execution_results"] = results

    elif execution_mode == "react":
        # Execute single step
        current_step = state.get("current_step", 0)

        # Get step to execute
        if current_step == 0:
            # First step: use initial_step from plan
            step = (
                state["planner_output"]
                .get("plan", {})
                .get("react", {})
                .get("initial_step", {})
            )
        else:
            # Subsequent steps: use next_step from planner_react
            step = state.get("next_step", {})

        # Execute step
        result = executor.execute_react_step(
            step=step,
            user_query=state["user_query"],
            previous_results=state.get("completed_steps", []),
        )

        # Add to completed steps
        if "completed_steps" not in state:
            state["completed_steps"] = []
        state["completed_steps"].append(result)

        # Increment step counter
        state["current_step"] = current_step + 1

        # Store results for next node
        state["execution_results"] = {
            "results": state["completed_steps"],
            "status": "success" if result["status"] == "success" else "partial",
            "metadata": {
                "execution_mode": "react",
                "current_step": state["current_step"],
                "total_steps": len(state["completed_steps"]),
            },
        }

    logger.info(
        "executor_node_complete",
        mode=execution_mode,
        status=state["execution_results"].get("status"),
    )

    return state


def upload_agent_node(state: ConversationState) -> ConversationState:
    """
    Upload agent node.

    Handles document ingestion steps from an upload_plan:
    InvoiceUploadTool, ContractUploadTool, BudgetUploadTool
    """
    upload_agent = UploadAgent()

    logger.info("upload_agent_node_executing")

    plan = state["planner_output"].get("plan", {})

    results = upload_agent.execute(
        plan=plan,
        user_query=state["user_query"],
        user_id=state.get("user_id", "default_user"),
    )

    state["execution_results"] = results

    logger.info(
        "upload_agent_node_complete",
        status=results.get("status"),
        steps_completed=results.get("metadata", {}).get("steps_completed"),
    )

    return state


def planner_react_node(state: ConversationState) -> ConversationState:
    """
    Planner ReAct node - plan next step based on previous results.

    Only called in ReAct mode.
    """
    planner = PlannerAgent()

    logger.info("planner_react_node_executing", current_step=state["current_step"])

    # Get strategy from initial plan
    strategy = (
        state["planner_output"].get("plan", {}).get("react", {}).get("strategy", "")
    )

    # Plan next step
    next_step_decision = planner.plan_next_step(
        user_query=state["user_query"],
        completed_steps=state["completed_steps"],
        current_results=(
            state["completed_steps"][-1] if state["completed_steps"] else {}
        ),
        strategy=strategy,
    )

    # Store decision
    state["react_continue"] = next_step_decision.get("continue", False)

    if state["react_continue"]:
        state["next_step"] = next_step_decision.get("next_step", {})
        logger.info("planner_react_continue", next_tool=state["next_step"].get("tool"))
    else:
        logger.info("planner_react_done", total_steps=len(state["completed_steps"]))

    return state


def validator_node(state: ConversationState) -> ConversationState:
    """
    Validator agent node.

    Validates response quality and provides feedback for retry loop.
    """
    validator = ValidatorAgent()

    logger.info("validator_node_executing")

    validation = validator.validate(
        user_query=state["user_query"],
        execution_results=state["execution_results"],
        plan=state["planner_output"].get("plan", {}),
    )

    state["validation_result"] = validation

    if not validation["valid"]:
        # Store feedback for Planner retry
        state["validation_feedback"] = {
            "issues": validation.get("issues", []),
            "retry_suggestion": validation.get("retry_suggestion", ""),
            "previous_results": state["execution_results"],
        }

        logger.warning(
            "validator_failed",
            issues=validation.get("issues"),
            retry_count=state.get("retry_count", 0),
        )
    else:
        logger.info("validator_passed")

    return state


def responder_node(state: ConversationState) -> ConversationState:
    """
    Responder agent node - format final response.

    Handles:
    - Generic responses (greetings, clarifications)
    - Execution results formatting
    - Error messages
    """
    responder = ResponderAgent()

    logger.info("responder_node_executing", route=state["route"])

    # Check route type
    if state["route"] == "generic_response":
        # Format generic response (hardcoded message)
        formatted = responder.format_generic_response()

    elif state["route"] == "clarification":
        # Format clarification (use planner's question)
        formatted = responder.format_clarification_response(
            state["planner_output"].get("response", "")
        )

    else:
        # Check if validation failed after max retries
        retry_count = state.get("retry_count", 0)
        validation_valid = state.get("validation_result", {}).get("valid", False)

        if retry_count >= 2 and not validation_valid:
            # Format error message
            formatted = responder.format_error_response(
                user_query=state["user_query"],
                issues=state.get("validation_feedback", {}).get("issues", []),
                retry_suggestion=state.get("validation_feedback", {}).get(
                    "retry_suggestion", ""
                ),
            )
        else:
            # Format validated execution results
            formatted = responder.format_response(
                user_query=state["user_query"],
                execution_results=state["execution_results"],
                metadata=state["execution_results"].get("metadata", {}),
                execution_mode=state.get("execution_mode", "one_way"),
            )

    # Store formatted response
    state["final_response"] = formatted["response"]
    state["display_format"] = formatted.get("display_format", "text")
    state["display_data"] = formatted.get("data")

    logger.info(
        "responder_node_complete",
        format=state["display_format"],
        has_data=bool(state["display_data"]),
    )

    return state


# ===== Routing Functions =====


def route_after_planner(state: ConversationState) -> str:
    """Route based on Planner's decision."""
    route = state["route"]

    if route == "generic_response":
        # Generic responses (greetings, out-of-scope) go to Responder (fast path)
        logger.info("route_fast_path", route=route)
        return "responder"
    elif route == "clarification":
        # Clarification questions go to Responder (fast path)
        logger.info("route_fast_path", route=route)
        return "responder"
    elif route == "execution_plan":
        # Data queries go to Executor
        logger.info("route_execution", mode=state.get("execution_mode"))
        return "executor"
    elif route == "upload_plan":
        # Document uploads go to UploadAgent
        logger.info("route_upload")
        return "upload_agent"

    # Default to responder
    return "responder"


def route_after_executor(state: ConversationState) -> str:
    """Route after Executor based on execution mode."""
    execution_mode = state.get("execution_mode", "one_way")

    if execution_mode == "one_way":
        # One-way done → validate
        logger.info("route_to_validator", mode="one_way")
        return "validator"

    elif execution_mode == "react":
        # Check max steps
        current_step = state.get("current_step", 0)
        max_steps = state.get("react_max_steps", 5)

        if current_step >= max_steps:
            # Max steps reached → validate
            logger.info(
                "route_to_validator", reason="max_steps_reached", steps=current_step
            )
            return "validator"

        # Ask planner for next step
        logger.info("route_to_planner_react", current_step=current_step)
        return "planner_react"

    return "validator"


def route_after_planner_react(state: ConversationState) -> str:
    """Route after ReAct planning."""
    if state.get("react_continue", False):
        # Continue ReAct loop
        logger.info("route_react_continue")
        return "executor"
    else:
        # Done → validate
        logger.info("route_react_done")
        return "validator"


def route_after_validator(state: ConversationState) -> str:
    """Route after Validator based on validation result."""
    is_valid = state.get("validation_result", {}).get("valid", False)
    retry_count = state.get("retry_count", 0)

    if is_valid:
        # Valid results → format response
        logger.info("route_to_responder", reason="valid")
        return "responder"
    else:
        # Check retry count
        if retry_count < 2:
            # Retry with feedback
            logger.info("route_retry", retry_count=retry_count)
            return "planner"
        else:
            # Max retries → format error
            logger.info("route_to_responder", reason="max_retries")
            return "responder"


# ===== Workflow Builder =====


def create_multi_agent_graph():
    """
    Create LangGraph workflow with four specialized agents.

    Returns:
        Compiled LangGraph workflow with checkpointer
    """
    logger.info("creating_multi_agent_graph")

    # Create workflow
    workflow = StateGraph(ConversationState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("upload_agent", upload_agent_node)
    workflow.add_node("planner_react", planner_react_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("responder", responder_node)

    # Set entry point
    workflow.set_entry_point("planner")

    # Add conditional edges
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "executor": "executor",
            "upload_agent": "upload_agent",
            "responder": "responder",
        },
    )

    # upload_agent → validator (same path as executor one_way)
    workflow.add_edge("upload_agent", "validator")

    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "validator": "validator",
            "planner_react": "planner_react",
        },
    )

    workflow.add_conditional_edges(
        "planner_react",
        route_after_planner_react,
        {
            "executor": "executor",
            "validator": "validator",
        },
    )

    workflow.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "planner": "planner",  # Retry loop
            "responder": "responder",
        },
    )

    # Responder always goes to END
    workflow.add_edge("responder", END)

    # Compile with checkpointer
    checkpointer = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=checkpointer)

    logger.info("multi_agent_graph_created")

    return compiled_graph
