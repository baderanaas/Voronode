# Multi-Agent Conversational System

This directory implements the LangGraph-based multi-agent system that handles all user chat interactions. It routes queries through specialized agents, executes tools against Neo4j and ChromaDB, and returns structured responses.

## Architecture Overview

```
User Query (+ optional file paths)
    ↓
[PLANNER]  ←──────────────────────────────────────────┐
    │  (Gemini 2.5 Pro)                                │
    │  Classifies intent AND document types            │ retry
    │  Decides route + execution mode                  │ (≤2x)
    ↓                                                  │
 ──────────────────────────────                        │
│           │              │                           │
▼           ▼              ▼                           │
[EXECUTOR] [UPLOAD_AGENT] [RESPONDER] ──→ END          │
    │           │                                      │
    ↓           ↓                                      │
[VALIDATOR]◄────┘                                      │
    │  (OpenAI GPT-4o-mini)                            │
    │  Checks result quality                           │
    │                                                  │
    ├── valid ──────→ [RESPONDER] ──→ END              │
    └── invalid ────────────────────────────────────────┘
```

### Who decides invoice vs contract vs budget?

The **Planner** does. When files are present in the request, the planner analyzes the message and file context and outputs an `upload_plan` with explicit steps like:

```json
{
  "route": "upload_plan",
  "plan": {
    "steps": [
      {"tool": "InvoiceUploadTool",  "action": "process|file_path=/tmp/abc.pdf"},
      {"tool": "ContractUploadTool", "action": "process|file_path=/tmp/xyz.pdf"}
    ]
  }
}
```

The `UploadAgent` is a pure executor — it reads the steps from the plan and runs them in order. It has no classification logic of its own.

### One-Way vs ReAct Execution

The planner picks one of two execution strategies per query:

- **One-Way**: Execute all planned steps sequentially in a single pass. Used when the plan is deterministic (e.g., "query Neo4j for X, then calculate Y").
- **ReAct**: Execute one step, then re-plan based on results. Used when the next action depends on what the current tool returns (up to 5 steps).

---

## Files

### Core Orchestration

| File | Description |
|------|-------------|
| `orchestrator.py` | Builds the LangGraph `StateGraph`, wires all nodes and conditional edges, exposes `create_multi_agent_graph()` |
| `state.py` | `ConversationState` TypedDict — the single object passed through the entire graph |

### Agents

| File | LLM | Role |
|------|-----|------|
| `planner_agent.py` | Gemini 2.5 Pro | Analyzes the user query, picks a route (`generic_response`, `execution_plan`, `clarification`, `upload_plan`), and builds a step-by-step plan |
| `executor_agent.py` | — | Runs tools with circuit breaker + timeout protection; supports both one-way and ReAct modes |
| `validator_agent.py` | OpenAI GPT-4o-mini | Semantic check that execution results actually answer the user's question |
| `responder_agent.py` | OpenAI GPT-4o-mini | Formats the final response and selects display format (`text`, `table`, `chart`) |
| `upload_agent.py` | — | Executes the upload steps defined by the Planner — does not classify document types |

### Tools (`tools/`)

| Tool | Description |
|------|-------------|
| `cypher_query_tool.py` | Generates and runs Cypher queries against Neo4j (uses Anthropic Claude Haiku 4.5) |
| `vector_search_tool.py` | Semantic search over ChromaDB invoice/contract/budget collections |
| `calculator_tool.py` | Safe arithmetic expressions |
| `graph_explorer_tool.py` | Explore Neo4j schema and relationships |
| `compliance_check_tool.py` | Ad-hoc contract compliance checks |
| `invoice_upload_tool.py` | Runs the invoice ingestion pipeline for an uploaded PDF |
| `contract_upload_tool.py` | Extracts and stores a contract PDF |
| `budget_upload_tool.py` | Extracts and stores a budget PDF |

### Prompts (`prompts/`)

Jinja2 templates rendered via `prompts/prompt_manager.py`:

```
prompts/
├── planner/
│   ├── analyze.j2              ← Initial query analysis + route decision
│   ├── retry_with_feedback.j2  ← Re-plan after validation failure
│   └── plan_next_step.j2       ← ReAct: decide next step from current results
├── cypher_tool/
│   └── generate_query.j2       ← Cypher generation prompt
├── responder/
│   ├── format_response.j2      ← Main response formatting
│   └── format_upload.j2        ← Upload confirmation message
└── common/
    ├── system_context.j2       ← Shared system context block
    └── macros.j2               ← Reusable Jinja2 macros
```

---

## State

`ConversationState` carries all data through the graph:

```python
class ConversationState(TypedDict):
    # Identity
    user_id: str

    # Input
    user_query: str
    conversation_history: list[dict]
    long_term_memories: list[str]

    # Planner outputs
    route: str                  # generic_response | execution_plan | clarification | upload_plan
    execution_mode: str         # one_way | react
    planner_output: dict        # Full plan with steps

    # Executor outputs
    execution_results: list[dict]
    completed_steps: list[dict] # ReAct: accumulated steps
    current_step: int

    # Validator outputs
    validation_result: bool
    validation_feedback: str    # Passed back to planner on retry

    # Responder outputs
    final_response: str
    display_format: str         # text | table | chart
    display_data: dict | None

    # Control
    retry_count: int            # Max 2 validator→planner retries
    react_continue: bool
    react_max_steps: int        # Default 5
```

---

## Resilience Patterns

### Circuit Breaker (per tool)
- 3 consecutive failures → circuit opens for 60 seconds
- Prevents a broken tool from stalling the entire conversation
- Managed by `backend/core/circuit_breaker.py`

### Tool Timeout
- Each tool call runs in a `ThreadPoolExecutor` with a 30-second timeout
- Timed-out tools return a user-friendly error instead of hanging

### Validator Retry Loop
- If the validator rejects results, the feedback is sent back to the planner
- The planner re-plans with the feedback (up to 2 retries before forcing a response)

---

## Adding a New Tool

1. Create `tools/my_tool.py` implementing `run(query, action, user_id, context) → dict`
2. Register it in `executor_agent.py` in `_load_tools()`
3. Add the tool name to the planner prompt so it knows the tool exists

---

## Adding a New Agent Node

1. Implement the node function with signature `(state: ConversationState) → dict`
2. Add it to the graph in `orchestrator.py` with `graph.add_node("name", fn)`
3. Wire edges/conditional edges from/to it
