# Voronode

AI-powered autonomous financial risk and compliance system for construction finance. Combines a multi-agent conversational interface with an automated document ingestion pipeline, backed by a Neo4j knowledge graph and multi-user JWT authentication.

## What it does

- **Chat with your financial data** — ask natural language questions about invoices, contracts, budgets, and contractors; agents query Neo4j or ChromaDB and format results as text, tables, or charts
- **Upload documents** — drop in PDF invoices, contracts, and budgets; an extraction pipeline structures them with LLMs, validates them, runs compliance audits against contract terms, and inserts them into the knowledge graph
- **Quarantine queue** — high-risk documents are flagged for human review before entering the graph; reviewers can approve, reject, or correct-and-retry
- **Multi-user** — JWT authentication with per-user data isolation across Neo4j, ChromaDB, and conversation history

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Streamlit Frontend  (port 8501)                                  │
│  Chat · Analytics · Graph Explorer · Quarantine Queue · Risk Feed │
└─────────────────────────┬────────────────────────────────────────┘
                          │  HTTP (JWT Bearer)
┌─────────────────────────▼────────────────────────────────────────┐
│  FastAPI Backend  (port 8080)                                     │
│  /api/auth  /api/chat  /api/conversations  /api/workflows         │
│  /api/graph  /api/analytics  /api/budgets  /api/health           │
└──────┬──────────────────┬────────────────────────────────────────┘
       │                  │
┌──────▼──────┐    ┌──────▼────────────────────────────────────────┐
│  Ingestion  │    │  Multi-Agent System  (LangGraph StateGraph)    │
│  Pipeline   │    │                                                │
│  Extract    │    │  PlannerAgent   → Gemini 2.5 Pro              │
│  Validate   │    │  ExecutorAgent  → 13 tools                    │
│  Audit      │    │  ValidatorAgent → GPT-4o-mini                 │
│  Insert     │    │  ResponderAgent → GPT-4o-mini                 │
└──────┬──────┘    └──────────────────────┬─────────────────────────┘
       │                                  │
┌──────▼──────────────────────────────────▼─────────────────────────┐
│  Data Layer                                                        │
│  Neo4j (knowledge graph)  ·  ChromaDB (vectors)  ·  Postgres (state)│
└───────────────────────────────────────────────────────────────────┘
```

### Multi-LLM strategy

| Role | Model | Reason |
|---|---|---|
| Planner | Gemini 2.5 Pro | Complex reasoning and routing |
| Validator / Responder | GPT-4o-mini | Fast, cost-effective formatting |
| Cypher generation | Claude Haiku 4.5 | Reliable Cypher synthesis |
| Document extraction | Groq Llama 3.3 70B | High-throughput structured extraction |

---

## Quick start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- API keys: Groq, OpenAI, Google Gemini, Anthropic

### 1. Clone and configure

```bash
git clone <repo-url>
cd voronode
cp .env.example .env
# Edit .env and fill in your API keys
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Start databases

```bash
cd docker && docker-compose up -d && cd ..
```

### 4. Initialize schemas

```bash
uv run python scripts/setup_neo4j.py
uv run python scripts/setup_chromadb.py
```

### 5. (Optional) Generate test fixtures

```bash
uv run python scripts/generate_test_data.py
```

Generates 10 invoice PDFs, 5 contracts, 3 budgets, 10 contractors, and 3 projects in `backend/tests/fixtures/`.

### 6. Run backend

```bash
uv run uvicorn backend.api.main:app --reload --port 8080
# Swagger UI: http://localhost:8080/docs
```

### 7. Run frontend

```bash
uv run streamlit run frontend/app.py
# Dashboard: http://localhost:8501
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the values below.

```bash
# LLM providers
GROQ_API_KEY=gsk_xxx
GROQ_MODEL=llama-3.3-70b-versatile
OPENAI_API_KEY=sk-xxx
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-2.5-pro
ANTHROPIC_API_KEY=sk-ant-xxx
TAVILY_API_KEY=tvly-xxx       # optional, enables web search

# Databases
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/voronode
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=voronode123
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

# Workflow
WORKFLOW_MAX_RETRIES=3
WORKFLOW_QUARANTINE_HIGH_RISK=true

# Compliance thresholds
ENABLE_COMPLIANCE_AUDIT=true
COMPLIANCE_PRICE_TOLERANCE_PERCENT=0.05
COMPLIANCE_RETENTION_TOLERANCE_PERCENT=0.01

# JWT auth
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=1440

# General
LOG_LEVEL=INFO
```

---

## Project structure

```
voronode/
├── backend/
│   ├── agents/
│   │   ├── orchestrator.py        # LangGraph StateGraph definition
│   │   ├── planner_agent.py       # Query routing & planning (Gemini)
│   │   ├── executor_agent.py      # Tool execution + circuit breaker
│   │   ├── validator_agent.py     # Result validation & retry feedback
│   │   ├── responder_agent.py     # Response formatting (text/table/chart)
│   │   ├── upload_agent.py        # Document processing pipeline
│   │   ├── tools/                 # 13 executor tools
│   │   └── prompts/               # Jinja2 prompt templates (.j2)
│   ├── api/
│   │   ├── main.py                # FastAPI app (CORS, startup)
│   │   ├── routes.py              # Router aggregator
│   │   └── routers/               # auth, chat, conversations, workflows,
│   │                              #   graph, analytics, budgets, health
│   ├── auth/
│   │   ├── user_store.py          # Postgres user CRUD
│   │   ├── utils.py               # JWT encode/decode, bcrypt hashing
│   │   └── dependencies.py        # FastAPI get_current_user() Depends
│   ├── core/
│   │   ├── config.py              # Pydantic settings from .env
│   │   ├── db.py                  # Connection pool (open/close/init_db)
│   │   ├── models.py              # Domain models (Invoice, Contract, …)
│   │   ├── state.py               # ConversationState TypedDict
│   │   └── circuit_breaker.py     # CircuitBreaker per tool
│   ├── ingestion/
│   │   ├── extractor.py           # PDF → structured Invoice (Groq)
│   │   ├── validator.py           # Anomaly detection (math + semantic)
│   │   ├── compliance_auditor.py  # Contract compliance checks
│   │   ├── contract_extractor.py  # Contract PDF → structured data
│   │   ├── budget_extractor.py    # Budget PDF/Excel → structured data
│   │   └── pipeline/              # LangGraph ingestion workflow nodes
│   ├── memory/
│   │   ├── conversation_store.py  # Postgres CRUD (conversations + messages)
│   │   └── mem0_client.py         # Mem0 semantic memory (ChromaDB-backed)
│   ├── services/
│   │   ├── llm_client.py          # Multi-LLM wrapper with retry backoff
│   │   ├── graph_builder.py       # Neo4j MERGE-based idempotent inserts
│   │   └── workflow_manager.py    # LangGraph checkpoint management
│   ├── graph/
│   │   ├── client.py              # Neo4j driver wrapper
│   │   └── schema.py              # Node/relationship definitions
│   ├── vector/
│   │   └── client.py              # ChromaDB HTTP client wrapper
│   └── tests/
│       ├── unit/                  # Models, compliance, agents
│       ├── integration/           # Pipeline, orchestrator, Cypher
│       ├── workflows/             # LangGraph workflow nodes & routing
│       ├── fixtures/              # PDFs, contracts, budgets, JSON
│       └── conftest.py            # Shared fixtures & mocks
├── frontend/
│   ├── app.py                     # Streamlit entry point + auth gate
│   ├── pages/
│   │   ├── Login.py               # Login / register tabs
│   │   ├── Chat.py                # Conversational AI + file upload
│   │   ├── Analytics.py           # Metrics & charts dashboard
│   │   ├── Graph_Explorer.py      # Interactive Cypher query builder
│   │   ├── Quarantine_Queue.py    # Invoice review (approve/reject/correct)
│   │   └── Risk_Feed.py           # Real-time processing monitor
│   ├── components/                # Anomaly badges, invoice cards, status UI
│   └── utils/
│       ├── api_client.py          # HTTP client (auth headers, error handling)
│       └── formatters.py          # Currency, datetime, status helpers
├── docker/
│   └── docker-compose.yml         # Neo4j + ChromaDB containers
├── scripts/                       # Setup & test data generation
├── data/                          # local scratch (git-ignored)
└── pyproject.toml
```

---

## Multi-agent chat system

User messages travel through a LangGraph StateGraph:

```
User message
    ↓
[Inject conversation history + Mem0 semantic memories]
    ↓
PlannerAgent  (Gemini 2.5 Pro)
    ├── route: generic_response  →  ResponderAgent  →  END
    ├── route: clarification     →  ResponderAgent  →  END
    └── route: execution_plan
          ↓
          execution_mode: one_way  OR  react (max 5 steps)
          ↓
    ExecutorAgent  (runs tools with 30s timeout + circuit breaker)
          ↓
    ValidatorAgent
          ├── valid  →  ResponderAgent  →  END
          └── invalid (retry < 2)  →  PlannerAgent  (with feedback)
          ↓
    ResponderAgent  (GPT-4o-mini)
          └── format: text | table | chart
          ↓
[Save turn to ConversationStore + extract facts to Mem0]
    ↓
Stream response to frontend
```

### Executor tools

| Tool | Purpose |
|---|---|
| `CypherQueryTool` | Generate + execute Neo4j Cypher (Claude Haiku 4.5) |
| `VectorSearchTool` | ChromaDB semantic search on indexed documents |
| `CalculatorTool` | Safe arithmetic evaluation |
| `DatetimeTool` | Date parsing, difference, formatting |
| `WebSearchTool` | Tavily web search (optional) |
| `PythonReplTool` | Restricted Python execution |
| `GraphExplorerTool` | Neo4j relationship traversal |
| `ComplianceCheckTool` | Validate invoice against contract terms |
| `InvoiceUploadTool` | Handle invoice PDF uploads |
| `ContractUploadTool` | Handle contract document uploads |
| `BudgetUploadTool` | Handle budget document uploads |
| `WorkflowTool` | Manage LangGraph workflow execution |
| `GraphExplorerTool` | Explore graph topology |

All tools: `.run(action, context, user_id)` · 30s timeout · circuit breaker (3 failures → 60s cooldown)

---

## Document ingestion pipeline

```
Upload PDF
    ↓
InvoiceExtractor  (pdfplumber → pypdf fallback → Groq Llama 3.3 70B)
    ↓
InvoiceValidator  (required fields · math checks · semantic LLM pass)
    ├── medium risk (< 3 retries)  →  Critic feedback → re-extract
    └── high / critical            →  Quarantine ⏸
    ↓
ComplianceAuditor  (runs against loaded Contract node)
    ├── retention rate  (±1% tolerance)
    ├── unit prices     (±5% tolerance)
    ├── billing cap     (total ≤ contract value)
    └── scope           (all cost codes approved)
    ├── critical / 2+ high  →  Quarantine ⏸
    └── clean
          ↓
GraphBuilder.insert_invoice()  (Neo4j MERGE, user_id tagged)
ChromaDBClient.add_documents() (vector embed)
Status: completed ✅
```

### Risk levels

| Level | Conditions | Action |
|---|---|---|
| Low | 0 high, < 3 medium anomalies | Auto-approve → graph |
| Medium | 1–2 medium anomalies | Retry with critic (max 3) |
| High | 1 high OR 3+ medium | Quarantine for review |
| Critical | 2+ high anomalies | Quarantine for review |

---

## API reference

### Authentication

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Register (username + password) |
| POST | `/api/auth/login` | Login → JWT token |
| GET | `/api/auth/me` | Current user info |

### Chat

| Method | Path | Description |
|---|---|---|
| POST | `/api/chat` | Send message (+ optional file attachments) |
| POST | `/api/chat/stream` | Streaming SSE variant |

### Conversations

| Method | Path | Description |
|---|---|---|
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations` | List user's conversations |
| GET | `/api/conversations/{id}` | Get conversation + messages |
| PATCH | `/api/conversations/{id}/title` | Rename |
| DELETE | `/api/conversations/{id}` | Delete (cascade) |

### Workflows

| Method | Path | Description |
|---|---|---|
| GET | `/api/workflows/quarantined` | List quarantined documents |
| POST | `/api/workflows/{id}/resume` | Approve / reject / correct-and-retry |
| GET | `/api/workflows/{id}/status` | Poll status |

### Graph

| Method | Path | Description |
|---|---|---|
| POST | `/api/graph/query` | Execute Cypher (user_id isolated) |
| GET | `/api/graph/stats` | Node/relationship counts |

### Other

| Method | Path | Description |
|---|---|---|
| GET | `/api/analytics/metrics` | Dashboard KPIs |
| GET | `/api/analytics/anomalies` | Anomaly distribution |
| GET | `/api/budgets` | List budgets |
| POST | `/api/budgets/upload` | Upload budget document |
| GET | `/api/health` | Neo4j + ChromaDB health check |

---

## Testing

```bash
# All tests
uv run pytest -v

# By suite
uv run pytest backend/tests/unit/       -v
uv run pytest backend/tests/integration/ -v
uv run pytest backend/tests/workflows/  -v
```

**Coverage**: 50+ tests across unit, integration, and workflow suites.

---

## Database schemas

### Neo4j nodes

All nodes include a `user_id` property for tenant isolation.

| Label | Key properties |
|---|---|
| `Invoice` | invoice_number, date, amount, status |
| `LineItem` | description, quantity, unit_price, cost_code |
| `Contract` | contractor_id, project_id, retention_rate |
| `Project` | name, budget, status |
| `Contractor` | name, license_number |
| `BudgetLine` | cost_code, allocated, spent |

**Relationships**: `ISSUED_BY`, `FOR_PROJECT`, `CONTAINS_ITEM`, `MAPS_TO`, `BINDS`, `HAS_BUDGET`

### Postgres (`DATABASE_URL`)

```sql
users         (id TEXT, username TEXT UNIQUE, hashed_pw TEXT, created_at TIMESTAMPTZ)
conversations (id TEXT, user_id TEXT, title TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
messages      (id TEXT, conversation_id TEXT REFERENCES conversations, role TEXT, content TEXT, created_at TIMESTAMPTZ)
workflow_states (document_id TEXT, user_id TEXT, status TEXT, paused BOOLEAN, risk_level TEXT, retry_count INT, state_json TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
-- LangGraph internal tables (checkpoints, writes, migrations) created by PostgresSaver.setup()
```

### ChromaDB collections

`invoices` · `contracts` · `memories` — all filtered by `user_id` metadata.

---

## Troubleshooting

**Workflow stuck in "processing"**
```bash
# Check LangGraph checkpoint tables in your Postgres DB (e.g. via Neon console)
# Tables: checkpoints, checkpoint_writes, checkpoint_migrations
```

**Database connection failures**
```bash
# Verify DATABASE_URL is set correctly in .env
uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL'); print('OK')"

cd docker && docker-compose restart
docker logs voronode-neo4j
docker logs voronode-chromadb
```

**Import errors after install**
```bash
uv sync
uv run python -c "from langgraph.checkpoint.postgres import PostgresSaver; print('OK')"
```

---

## Roadmap

### Completed
- Phase 1: Knowledge Foundation (Neo4j + ChromaDB)
- Phase 2: Document Intelligence (PDF extraction + validation)
- Phase 3: LangGraph Orchestration (workflow + quarantine)
- Phase 4A: Streamlit Dashboard (5 pages)
- Phase 4B: Contract Compliance Auditor
- Multi-agent conversational AI (Planner → Executor → Validator → Responder)
- JWT authentication & per-user data isolation
- Persistent memory (Mem0 + Postgres conversation store)

### Planned
- [ ] React / Next.js frontend migration
- [ ] Celery async job processing
- [ ] Prometheus metrics & Grafana dashboards
- [ ] RAG-powered critic with historical knowledge
- [ ] Predictive risk modeling
- [ ] Batch multi-document processing
- [ ] AI Benchmarking Agent (cost-vs-historical comparison)
- [ ] Cost-to-Complete Forecaster (burn rate projections)

---

**Stack:** FastAPI · LangGraph · Streamlit · Neo4j · ChromaDB · Neon Postgres · Gemini · OpenAI · Anthropic · Groq · Mem0 · python-jose
