# Voronode Backend

The backend is a FastAPI application built around two LangGraph pipelines: a **multi-agent chat system** that handles user queries, and a **document ingestion pipeline** that processes PDF uploads. Both write to shared Neo4j and ChromaDB backends and are scoped per user via JWT authentication.

---

## System Map

```
┌──────────────────────────────────────────────────────────────┐
│                      Streamlit Frontend                       │
│           Chat  ·  Analytics  ·  Graph Explorer              │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼───────────────────────────────────┐
│                     FastAPI  (api/)                           │
│   /auth   /chat   /workflows   /analytics   /graph           │
│   JWT auth ─ get_current_user() on every request             │
└────────┬─────────────────┬────────────────────────────────────┘
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌─────────────────────────────────────────┐
│  CHAT ENDPOINT  │  │         WORKFLOW ENDPOINTS               │
│  /api/chat      │  │  GET  /quarantined                       │
│                 │  │  POST /{id}/resume                       │
│  1. Load history│  │  GET  /{id}/status                       │
│  2. Load Mem0   │  └──────────────────┬──────────────────────┘
│  3. invoke()    │                     │
└────────┬────────┘                     │
         │                             │
         ▼                             ▼
┌─────────────────────────────────────────────────────────────┐
│           MULTI-AGENT SYSTEM  (agents/)                      │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌───────────┐              │
│  │ PLANNER  │──▶│ EXECUTOR │──▶│ VALIDATOR │              │
│  │ Gemini   │   │          │   │  OpenAI   │              │
│  └──────────┘   └────┬─────┘   └─────┬─────┘              │
│       ▲              │               │                     │
│       │   ┌──────────┘    valid      ▼                     │
│  retry│   │           ┌──────────────────┐                 │
│  (≤2x)│   │           │    RESPONDER     │                 │
│       └───┘ invalid   │    OpenAI        │──▶ response     │
│                       └──────────────────┘                 │
│                                                             │
│  ┌─────────────────────────────────────────────┐           │
│  │  UPLOAD AGENT  (triggered by file uploads)  │           │
│  │  Invoice Tool ─ Contract Tool ─ Budget Tool │           │
│  └──────────────────────┬──────────────────────┘           │
└─────────────────────────┼───────────────────────────────────┘
                          │  (each upload tool calls ↓)
┌─────────────────────────▼───────────────────────────────────┐
│          INGESTION PIPELINE  (ingestion/)                    │
│                                                             │
│  PDF ──▶ extract_text ──▶ structure_invoice                 │
│                │               │                            │
│           (Groq LLM)      validate_invoice                  │
│                                │                            │
│                       ┌────────┴────────┐                   │
│                       │                 │                   │
│                 compliance_audit    quarantine               │
│                       │             (human review)          │
│                  insert_graph                               │
│                       │                                     │
│                  embed_vector ──▶ finalize                  │
└─────────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Neo4j      │  │  ChromaDB    │  │  Postgres    │
│  Graph DB    │  │  Vectors     │  │ Convs · Auth │
│  Invoices    │  │  Embeddings  │  │ Checkpoints  │
│  Contracts   │  │  Semantic    │  │              │
│  Projects    │  │  Search      │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Directory Structure

```
backend/
├── api/
│   ├── main.py                  ← FastAPI app init, middleware, router mounting
│   ├── routes.py                ← Aggregates all routers
│   └── routers/
│       ├── auth.py              ← /auth/register, /auth/login, /auth/me
│       ├── chat.py              ← /chat (streaming + file upload)
│       ├── workflows.py         ← /workflows (quarantine, resume, status)
│       ├── analytics.py         ← /analytics
│       └── graph.py             ← /graph
│
├── agents/                      ← Multi-agent chat system (see agents/README.md)
│   ├── orchestrator.py
│   ├── state.py
│   ├── planner_agent.py
│   ├── executor_agent.py
│   ├── validator_agent.py
│   ├── responder_agent.py
│   ├── upload_agent.py
│   ├── prompts/
│   └── tools/
│
├── ingestion/                   ← Document ingestion pipeline (see ingestion/README.md)
│   ├── extractor.py
│   ├── validator.py
│   ├── compliance_auditor.py
│   ├── budget_extractor.py
│   ├── contract_extractor.py
│   └── pipeline/
│       ├── invoice_workflow.py
│       ├── nodes.py
│       ├── routing.py
│       └── config.py
│
├── auth/
│   ├── user_store.py            ← Postgres users table
│   ├── utils.py                 ← JWT encode/decode + bcrypt hashing
│   └── dependencies.py          ← get_current_user FastAPI dependency
│
├── core/
│   ├── config.py                ← Pydantic settings (loaded from .env)
│   ├── db.py                    ← Shared ConnectionPool — open_pool(), close_pool(), init_db()
│   ├── models.py                ← Invoice, LineItem, Contract, Budget Pydantic models
│   ├── state.py                 ← WorkflowState TypedDict
│   ├── logging.py               ← Shim → voronode_logging package
│   └── circuit_breaker.py      ← Per-tool circuit breaker manager
│
├── memory/
│   ├── conversation_store.py    ← Postgres CRUD for conversation history
│   └── mem0_client.py           ← Mem0 semantic memory (user_id scoped)
│
├── services/
│   ├── llm_client.py            ← Gemini, OpenAI, Anthropic, Groq clients with retry
│   ├── graph_builder.py         ← Neo4j MERGE-based node/relationship creation
│   └── workflow_manager.py      ← Workflow state persistence + quarantine tracking
│
├── graph/
│   └── client.py                ← Neo4j driver singleton
│
└── vector/
    └── client.py                ← ChromaDB client singleton
```

---

## The Two Pipelines

### Multi-Agent Chat (`agents/`)

Handles real-time user queries. Entry point: `orchestrator.create_multi_agent_graph()`.

**Flow**: User query → Planner (route + plan) → Executor (tools) → Validator (quality check) → Responder (format)

Key characteristics:
- Planner uses **Gemini 2.5 Pro** for complex reasoning and dynamic planning
- Two execution modes: **one-way** (sequential) and **ReAct** (step-by-step with re-planning)
- Circuit breaker + 30s timeout on every tool call
- Validator can reject results and send feedback back to the planner (up to 2 retries)
- Display format selection: `text`, `table`, or `chart` depending on result type

See [`agents/README.md`](agents/README.md) for full details.

### Document Ingestion (`ingestion/`)

Processes PDF uploads through extraction → validation → compliance → storage. Entry point: `pipeline/invoice_workflow.build_invoice_workflow()`.

**Flow**: PDF → extract text → structure with LLM → validate → compliance check → Neo4j + ChromaDB

Key characteristics:
- **Groq Llama 3.3 70B** for fast invoice structuring from raw text
- Critic loop: anomalies trigger LLM-generated feedback and re-extraction (up to 3 retries)
- Risk-based routing: low → proceed, medium → retry, high/critical → quarantine
- Postgres checkpointing enables pause/resume for quarantined documents
- All nodes are non-fatal for ChromaDB (embed failure doesn't block graph insert)

See [`ingestion/README.md`](ingestion/README.md) for full details.

---

## How They Connect

When a user uploads a PDF via the chat interface:

1. The `/chat` endpoint passes the file paths and user message into `ConversationState`
2. The **Planner** (Gemini 2.5 Pro) reads the message and file context and decides:
   - Route: `upload_plan`
   - Document type per file: `InvoiceUploadTool`, `ContractUploadTool`, or `BudgetUploadTool`
   - Outputs a plan with explicit steps and file paths
3. The **Upload Agent** receives the plan and executes the steps in order — it is a pure executor with no classification logic
4. Each upload tool runs the ingestion pipeline (`build_invoice_workflow()` or equivalent)
5. Results flow to the **Validator** then **Responder**, which formats a confirmation message back to the user

This means a single chat message can trigger both pipelines simultaneously if multiple file types are uploaded.

---

## LLM Model Assignment

| Task | Model | Rationale |
|------|-------|-----------|
| Query planning & reasoning | Gemini 2.5 Pro | Best at ambiguous, open-ended planning |
| Response formatting + validation | OpenAI GPT-4o-mini | Fast and cost-effective |
| Cypher query generation | Anthropic Claude Haiku 4.5 | Reliable Cypher syntax |
| Document structuring | Groq Llama 3.3 70B | Fast inference for extraction tasks |

---

## Multi-Tenancy

Every piece of data is scoped by `user_id`:
- **Neo4j**: All Invoice, Contract, Budget, Project nodes have a `user_id` property
- **ChromaDB**: Metadata filters on `user_id` in every collection
- **Mem0**: Facts stored and retrieved per `user_id`
- **Postgres**: Conversations, messages, and users tables all have `user_id NOT NULL`
- **API**: `user_id` sourced from JWT `sub` claim via `get_current_user()`

---

## Running the Backend

```bash
# Install dependencies
pip install -e .

# Start the API
uvicorn backend.api.main:app --reload --port 8000
```

Required environment variables (see `backend/core/config.py` for full list):

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/voronode
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...
JWT_SECRET_KEY=...
```
