# Voronode - Autonomous Financial Risk & Compliance System

AI-powered multi-agent system for construction financial oversight using GraphRAG and LangGraph orchestration.

## Architecture

- **Knowledge Graph:** Neo4j (relationships between projects, invoices, contracts)
- **Vector Store:** ChromaDB (unstructured document search with embeddings)
- **LLM:** Groq (llama-3.3-70b for reasoning and extraction)
- **Orchestration:** LangGraph (conditional workflows with human-in-the-loop)
- **API:** FastAPI (RESTful endpoints for invoice processing)

## Implementation Status

### Phase 1: Knowledge Foundation ✅

- Graph schema defined (Projects, Invoices, Contractors, BudgetLines, etc.)
- Database infrastructure (Neo4j + ChromaDB via Docker)
- Core Pydantic models with validation
- Synthetic test data generation (10 invoice PDFs, 5 contracts, 3 project budgets, 10 contractors)
- Database client wrappers

### Phase 2: Document Intelligence Agent ✅

- PDF text extraction (pdfplumber + pypdf fallback)
- LLM-powered invoice structuring with Groq
- Comprehensive validation (math checks, semantic validation)
- Neo4j graph insertion with idempotent merges
- ChromaDB vector embeddings
- FastAPI endpoints (`/invoices/upload`, `/invoices/{id}`, `/health`)
- **12 integration tests passing**

### Phase 3: LangGraph Orchestration ✅

- Conditional routing based on risk levels (low/medium/high/critical)
- Automatic retry logic with critic agent feedback (max 3 retries)
- Human-in-the-loop workflow pausing for high-risk invoices
- Complete state persistence with SQLite checkpoints
- Quarantine management endpoints
- **26 workflow tests passing** (100% pass rate)

### Phase 4: UI & Compliance Auditor ✅

**Phase 4A: Streamlit Dashboard**
- 5-page multi-page Streamlit application for financial oversight teams
- **Risk Feed:** Real-time monitoring of invoice processing and anomaly alerts
- **Quarantine Queue:** Interactive approve/reject interface with corrections editor
- **Upload Invoice:** PDF upload with progress tracking and workflow visualization
- **Graph Explorer:** Neo4j visualization with custom Cypher queries
- **Analytics:** Processing metrics, trends, and anomaly distribution charts
- Reusable UI components (invoice cards, anomaly badges, workflow status)
- API client wrapper with error handling and caching

**Phase 4B: Contract Compliance Auditor**
- Automated validation of invoices against contract terms
- **Retention Rate Validation:** Verify retention calculations match contract terms
- **Unit Price Validation:** Check line items against contract price schedules (5% tolerance)
- **Billing Cap Enforcement:** Prevent invoices from exceeding contract values
- **Scope Validation:** Ensure all cost codes are within approved scope
- Integrated into LangGraph workflow between validation and graph insertion
- Configurable thresholds for quarantine triggers
- **15+ compliance tests passing** (>90% coverage)

**Total Tests:** 58+ passing (includes compliance auditor unit tests)

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Groq API key ([get one here](https://console.groq.com))
- OpenAI API key (for embeddings)

### Installation

1. **Clone and enter directory:**
```bash
git clone <repo-url>
cd voronode
```

2. **Create `.env` file:**
```bash
cp .env.example .env
```

Add your API keys:
```bash
GROQ_API_KEY=gsk_xxx
OPENAI_API_KEY=sk-xxx
NEO4J_PASSWORD=voronode123
```

3. **Install dependencies:**
```bash
uv sync
```

4. **Start databases:**
```bash
cd docker
docker-compose up -d
cd ..
```

5. **Initialize schemas:**
```bash
uv run python scripts/setup_neo4j.py
uv run python scripts/setup_chromadb.py
```

6. **Generate test data (optional):**
```bash
uv run python scripts/generate_test_data.py
```
Generates 10 invoice PDFs with JSON metadata, 5 contracts, 3 project budgets, 10 contractors, and 3 projects in `backend/tests/fixtures/`.

### Verify Setup

```bash
# Run all tests
uv run pytest

# Check Neo4j browser: http://localhost:7474
# User: neo4j, Password: voronode123

# Check ChromaDB: http://localhost:8000/api/v1/heartbeat
```

## API Usage

### Start the Backend API Server

```bash
uv run uvicorn backend.api.main:app --reload --port 8080
```

API docs available at: http://localhost:8080/docs

### Start the Streamlit Dashboard (Phase 4)

```bash
uv run streamlit run frontend/app.py
```

Dashboard available at: http://localhost:8501

**Dashboard Features:**
- Monitor real-time risk alerts and processing metrics
- Review and approve quarantined invoices through the UI
- Upload new invoices with visual progress tracking
- Explore the knowledge graph with interactive visualizations
- View analytics and trends across all processed invoices

### Upload Invoice (LangGraph Workflow)

**Option 1: Via Streamlit Dashboard (Recommended)**
1. Navigate to http://localhost:8501
2. Go to "Upload Invoice" page
3. Drag and drop PDF or use file picker
4. Monitor processing in real-time
5. Review extracted data and anomalies

**Option 2: Via API**
```bash
curl -X POST http://localhost:8080/api/upload \
  -F "file=@invoice.pdf"
```

**Response:**
```json
{
  "success": true,
  "workflow_id": "abc-123",
  "invoice_number": "INV-2024-0001",
  "amount": 10000.00,
  "risk_level": "low",
  "requires_review": false,
  "retry_count": 0,
  "processing_time_seconds": 8.42
}
```

### Manage Quarantined Invoices

**Option 1: Via Streamlit Dashboard (Recommended)**
1. Go to "Quarantine Queue" page
2. Review anomalies and extracted data
3. Choose action:
   - **Approve:** Accept invoice as-is
   - **Reject:** Mark as invalid with notes
   - **Correct & Retry:** Edit fields and re-process

**Option 2: Via API**

**Check Quarantine Queue:**
```bash
curl http://localhost:8080/api/workflows/quarantined
```

**Approve Workflow:**
```bash
curl -X POST http://localhost:8080/api/workflows/{workflow_id}/resume \
  -H "Content-Type: application/json" \
  -d '{
    "action": "approve",
    "notes": "Verified with contractor"
  }'
```

**Apply Corrections:**
```bash
curl -X POST http://localhost:8080/api/workflows/{workflow_id}/resume \
  -H "Content-Type: application/json" \
  -d '{
    "action": "correct",
    "corrections": {"total_amount": 10000.00},
    "notes": "Corrected total amount"
  }'
```

**Get Workflow Status:**
```bash
curl http://localhost:8080/api/workflows/{workflow_id}
```

## Workflow Architecture

### LangGraph State Machine (Phase 4 with Compliance Audit)

```
Upload Invoice
    ↓
Extract Text (pdfplumber)
    ↓
Structure Invoice (LLM)
    ├─ Success → Validate
    ├─ Failure (retry < 3) → Critic Agent → Retry
    └─ Failure (retry = 3) → Quarantine (Human Review)
    ↓
Validate Invoice (Anomaly Detection)
    ├─ Low Risk → Compliance Audit
    ├─ Medium Risk (retry < 3) → Critic Agent → Retry
    └─ High/Critical Risk → Quarantine (Human Review) ⏸️
    ↓
Compliance Audit (NEW in Phase 4B)
    ├─ Clean → Insert Graph → Embed Vector → Complete ✅
    └─ Violations (Critical/High) → Quarantine (Human Review) ⏸️
```

**Compliance Checks:**
1. **Retention Rate:** Invoice retention matches contract terms
2. **Unit Prices:** Line item prices within contract schedule (±5% tolerance)
3. **Billing Cap:** Total billing doesn't exceed contract value
4. **Scope:** All cost codes are approved for this contract

### Risk Level Calculation

| Risk Level | Conditions | Action |
|------------|-----------|--------|
| **Low** | 0 high, <3 medium anomalies | Auto-approve → Graph |
| **Medium** | 1-2 medium anomalies | Retry with critic |
| **High** | 1 high OR 3+ medium | Quarantine for review |
| **Critical** | 2+ high anomalies | Quarantine for review |

### Anomaly Types

**Validation Anomalies:**
- **High Severity:** Math errors, missing fields, total mismatches
- **Medium Severity:** Future dates, invalid due dates, semantic mismatches
- **Low Severity:** Invalid invoice number format, minor formatting issues

**Compliance Anomalies (Phase 4B):**
- **Critical:** Billing cap exceeded by >10%, contract not found
- **High:** Unit price exceeds contract by >10%, retention violations >10%, out-of-scope charges
- **Medium:** Price mismatches 5-10%, retention mismatches 1-10%
- **Low:** Minor deviations within tolerance

## Project Structure

```
voronode/
├── backend/
│   ├── core/           # Config, models, state definitions
│   ├── db/             # Neo4j client & schema
│   ├── vector/         # ChromaDB client
│   ├── agents/         # Extractor, validator, compliance auditor
│   ├── services/       # LLM client, graph builder
│   ├── workflows/      # LangGraph nodes, routing, workflow definition
│   ├── api/            # FastAPI routes & schemas
│   └── tests/
│       ├── unit/       # Model, schema, compliance tests
│       ├── integration/# Pipeline tests
│       └── workflows/  # LangGraph workflow tests
├── frontend/           # Streamlit dashboard (Phase 4A)
│   ├── pages/          # Risk Feed, Quarantine Queue, Upload, Graph Explorer, Analytics
│   ├── components/     # Reusable UI components
│   ├── utils/          # API client, formatters
│   └── app.py          # Main entry point
├── scripts/            # Setup & data generation
├── docker/             # Database containers
├── examples/           # Demo scripts
└── README.md

### Test Fixtures

```
backend/tests/fixtures/
├── invoices/           # 10 invoice PDFs + JSON metadata
│   ├── INV-2024-0001.pdf / .json
│   └── ...
├── contracts/          # 5 contract JSON files
│   ├── CONTRACT-001.json  (Schultz LLC → South Alyssa Tower, clean pass)
│   ├── CONTRACT-002.json  (Baxter LLC → West George Tower, clean pass)
│   ├── CONTRACT-003.json  (Edwards-James → South Alyssa Tower, scope violation)
│   ├── CONTRACT-004.json  (Paul, Kelley and Simmons → Sheltonhaven Tower, price violation)
│   └── CONTRACT-005.json  (Gates Inc → Sheltonhaven Tower, near billing cap)
├── budgets/            # Per-project budget lines
│   ├── PRJ-001-budgets.json  (South Alyssa Tower, 4 cost codes)
│   ├── PRJ-002-budgets.json  (West George Tower, 3 cost codes)
│   └── PRJ-003-budgets.json  (Sheltonhaven Tower, 4 cost codes)
├── projects.json       # 3 active construction projects
└── contractors.json    # 10 contractors with license numbers
```

Contracts are designed to create realistic compliance scenarios: clean passes, unit price violations, scope violations (unapproved cost codes), and near-cap billing.
```

## API Endpoints

### Invoice Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/invoices/upload-graph` | POST | Upload invoice with LangGraph workflow |
| `/api/invoices/upload` | POST | Legacy sequential pipeline |
| `/api/invoices/{id}` | GET | Get invoice details from Neo4j |

### Workflow Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflows/quarantined` | GET | List workflows awaiting review |
| `/api/workflows/{id}/resume` | POST | Resume with human feedback |
| `/api/workflows/{id}/status` | GET | Poll workflow status |

### Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Check Neo4j & ChromaDB connectivity |

## Configuration

### Environment Variables

```bash
# LLM
GROQ_API_KEY=gsk_xxx
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_RETRIES=3

# Embeddings
OPENAI_API_KEY=sk-xxx
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=voronode123

# ChromaDB
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

# Workflow (Phase 3)
WORKFLOW_MAX_RETRIES=3
WORKFLOW_CHECKPOINT_DB=workflow_checkpoints.db
WORKFLOW_STATE_DB=workflow_states.db
WORKFLOW_QUARANTINE_HIGH_RISK=true

# Compliance Auditor (Phase 4B)
ENABLE_COMPLIANCE_AUDIT=true
COMPLIANCE_PRICE_TOLERANCE_PERCENT=0.05  # 5% tolerance
COMPLIANCE_RETENTION_TOLERANCE_PERCENT=0.01  # 1% tolerance
COMPLIANCE_QUARANTINE_ON_VIOLATION=true
COMPLIANCE_CRITICAL_THRESHOLD=1  # Quarantine if 1+ critical violations
COMPLIANCE_HIGH_THRESHOLD=2  # Quarantine if 2+ high violations

# API
API_UPLOAD_MAX_SIZE=10485760  # 10MB
```

## Testing

### Run All Tests

```bash
uv run pytest -v
```

### Run Specific Test Suites

```bash
# Unit tests
uv run pytest backend/tests/unit/ -v

# Integration tests
uv run pytest backend/tests/integration/ -v

# Workflow tests
uv run pytest backend/tests/workflows/ -v
```

### Test Coverage

```bash
# Phase 1: Unit tests (6/6 passing)
uv run pytest backend/tests/unit/test_models.py -v

# Phase 2: Integration tests (11/12 passing)
uv run pytest backend/tests/integration/ -v

# Phase 3: Workflow tests (26/26 passing)
uv run pytest backend/tests/workflows/ -v

# Phase 4B: Compliance tests (15+ tests passing)
uv run pytest backend/tests/unit/test_compliance_auditor.py -v
```

## Development

### Adding New Workflow Nodes

1. Define node function in `backend/workflows/nodes.py`:
```python
def my_custom_node(state: WorkflowState) -> Dict[str, Any]:
    # Process state
    return {"field": "value"}
```

2. Add to graph in `backend/workflows/invoice_workflow.py`:
```python
workflow.add_node("my_custom", my_custom_node)
workflow.add_edge("previous_node", "my_custom")
```

3. Add tests in `backend/tests/workflows/test_nodes.py`

### Modifying Routing Logic

Edit `backend/workflows/routing.py` to change conditional routing decisions.

### Customizing Validation

Add new validation checks in `backend/agents/validator.py`:
```python
def _validate_custom(self, invoice: Invoice) -> List[ValidationAnomaly]:
    # Custom validation logic
    pass
```

## Database Queries

### Neo4j (Cypher)

```cypher
// Find all invoices for a contractor
MATCH (c:Contractor)-[:ISSUED]->(i:Invoice)
WHERE c.name = "ABC Construction"
RETURN i

// Find budget overruns
MATCH (p:Project)-[:HAS_BUDGET]->(bl:BudgetLine)
WHERE bl.spent > bl.allocated
RETURN p.name, bl.cost_code, bl.spent - bl.allocated AS overrun

// Invoice line items with cost codes
MATCH (i:Invoice)-[:CONTAINS_ITEM]->(li:LineItem)-[:MAPS_TO]->(bl:BudgetLine)
RETURN i.invoice_number, li.description, bl.cost_code
```

### ChromaDB (Vector Search)

```python
from backend.vector.client import ChromaDBClient

client = ChromaDBClient()
results = client.search_documents(
    collection_name="invoices",
    query_text="plumbing work in January 2024",
    n_results=5
)
```

### Workflow State (SQLite)

```sql
-- List all quarantined workflows
SELECT * FROM workflow_states WHERE paused = 1;

-- Count workflows by status
SELECT status, COUNT(*) FROM workflow_states GROUP BY status;

-- Find high-risk workflows
SELECT * FROM workflow_states WHERE risk_level = 'high';
```

## Performance

### Typical Processing Times

| Scenario | Time | Notes |
|----------|------|-------|
| Clean invoice (low risk) | 5-10s | No retries needed |
| Medium risk (1 retry) | 15-20s | Includes critic feedback |
| High risk (quarantined) | ∞ | Awaits human review |

### Retry Budget

- LLM retries: 3x per attempt (Groq client)
- Workflow retries: 3x per workflow
- Total possible LLM calls: 9-12 max

## Troubleshooting

### Workflow Stuck in "processing"

```bash
# Check checkpoint database
sqlite3 workflow_checkpoints.db "SELECT * FROM checkpoints;"

# Clear corrupted checkpoints
rm workflow_checkpoints.db
```

### Quarantined Workflows Not Showing

```bash
# Query state database directly
sqlite3 workflow_states.db "SELECT * FROM workflow_states WHERE paused = 1;"
```

### Import Errors

```bash
# Ensure all dependencies installed
uv sync

# Verify langgraph checkpoint package
uv run python -c "from langgraph.checkpoint.sqlite import SqliteSaver; print('OK')"
```

### Database Connection Issues

```bash
# Restart Docker containers
cd docker && docker-compose restart

# Check Neo4j logs
docker logs voronode-neo4j

# Check ChromaDB logs
docker logs voronode-chromadb
```

## Examples

See `examples/workflow_demo.py` for complete usage examples including:
- Uploading invoices with workflow
- Monitoring quarantine queue
- Resuming workflows with human feedback
- Polling workflow status

## Roadmap

### Completed
- ✅ Phase 1: Knowledge Foundation
- ✅ Phase 2: Document Intelligence Agent
- ✅ Phase 3: LangGraph Orchestration
- ✅ Phase 4A: Streamlit Dashboard
- ✅ Phase 4B: Contract Compliance Auditor

### Future Enhancements (Phase 5+)
- [ ] **Additional Agents:**
  - [ ] AI Benchmarking Agent (compare costs to historical data)
  - [ ] Cost-to-Complete Forecaster (burn rate + projections)
  - [ ] Automated contract term extraction from PDFs
- [ ] **Production Hardening:**
  - [ ] React/Next.js migration for external users
  - [ ] Multi-tenancy and RBAC
  - [ ] Async job processing with Celery/RQ
  - [ ] Audit logging
  - [ ] Prometheus metrics & Grafana dashboards
- [ ] **Intelligence:**
  - [ ] RAG-powered critic with historical knowledge
  - [ ] Predictive risk modeling
  - [ ] Workflow visualization (real-time Mermaid diagrams)
  - [ ] Multi-document batch processing
  - [ ] Cost tracking (LLM token usage)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `uv run pytest`
5. Submit a pull request

## License

See LICENSE file.

## Support

- **Streamlit Dashboard:** http://localhost:8501 (Phase 4)
- **API Documentation:** http://localhost:8080/docs (when server is running)
- **Neo4j Browser:** http://localhost:7474
- **ChromaDB API:** http://localhost:8000/docs
- **Issues:** GitHub Issues

---

**Built with:** LangGraph • Streamlit • FastAPI • Neo4j • ChromaDB • Groq • OpenAI
