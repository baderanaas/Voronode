# Document Ingestion Pipeline

This directory implements the LangGraph-based document processing pipeline. It takes PDF uploads, extracts structured data, validates quality, checks contract compliance, and stores results in Neo4j and ChromaDB. Problematic documents are quarantined for human review instead of silently failing.

## Architecture Overview

```
PDF Upload
    ↓
[extract_text]          ← pdfplumber → raw text
    ↓
[structure_invoice]     ← Groq Llama 3.3 70B → Invoice schema
    ↓
[should_retry_extraction?]
    ├── complete   ──→ [validate_invoice]
    ├── retryable  ──→ [critic_agent] ──→ back to structure_invoice (≤3x)
    └── failed     ──→ [quarantine]
         ↓
[validate_invoice]      ← field checks, date logic, line item math
    ↓
[route_by_validation_severity]
    ├── low    ──→ [compliance_audit]
    ├── medium ──→ [critic_agent] ──→ back to structure_invoice (≤3x)
    └── high   ──→ [quarantine]
         ↓
[compliance_audit]      ← fetches contract from Neo4j, checks terms
    ↓
[route_by_compliance_severity]
    ├── clean     ──→ [insert_graph]
    ├── warnings  ──→ [insert_graph]
    └── critical  ──→ [quarantine]
         ↓
[insert_graph]          ← Neo4j: Invoice, LineItem, Contractor, Project nodes
    ↓
[embed_vector]          ← ChromaDB: full-text embedding
    ↓
[finalize]              ← status = completed / quarantined
    ↓
END
```

---

## Files

### Pipeline (`pipeline/`)

| File | Description |
|------|-------------|
| `invoice_workflow.py` | Builds and compiles the LangGraph `StateGraph`; exports `build_invoice_workflow()` |
| `nodes.py` | All 10 node implementations — the actual processing logic lives here |
| `routing.py` | 6 conditional routing functions that decide graph edges at runtime |
| `config.py` | `WorkflowConfig` dataclass: retry limits, compliance thresholds, feature flags |

### Extraction & Validation

| File | Description |
|------|-------------|
| `extractor.py` | `InvoiceExtractor` — PDF text extraction + LLM structuring into `Invoice` schema |
| `validator.py` | `InvoiceValidator` — field presence, date logic, line item math, total summation |
| `compliance_auditor.py` | `ComplianceAuditor` — retention rate, unit prices, billing cap, cost code scope |
| `budget_extractor.py` | Equivalent extractor for budget PDFs |
| `contract_extractor.py` | Equivalent extractor for contract PDFs |

---

## Nodes Reference

| Node | Input | Output | Notes |
|------|-------|--------|-------|
| `extract_text` | `document_path` | `raw_text` | pdfplumber with pypdf fallback |
| `structure_invoice` | `raw_text`, `critic_feedback?` | `extracted_data`, `extraction_confidence` | Groq Llama 3.3 70B |
| `critic_agent` | `anomalies[]` | `critic_feedback`, `retry_count++` | LLM-generated correction feedback |
| `validate_invoice` | `extracted_data` | `anomalies[]`, `risk_level` | Pure Python checks |
| `compliance_audit` | `extracted_data`, `contract_id` | `compliance_anomalies[]`, updated `risk_level` | Neo4j contract lookup |
| `quarantine` | current state | `status=quarantined`, `paused=true` | Halts for human review |
| `insert_graph` | `extracted_data`, `user_id` | `neo4j_id`, `graph_updated` | MERGE-based idempotent |
| `embed_vector` | `extracted_data` | — | Non-fatal; skipped if fails |
| `finalize` | final state | `final_report`, `status=completed` | Saves SQLite checkpoint |
| `error_handler` | `error` | `status=failed` | Critical failures only |

---

## State

`WorkflowState` is the TypedDict passed through the graph:

```python
class WorkflowState(TypedDict):
    # Identity
    user_id: str
    document_id: str
    document_path: str
    document_type: str          # invoice | contract | budget

    # Extraction
    raw_text: str
    extracted_data: dict        # Serialized Invoice model
    extraction_confidence: float

    # Validation
    validation_results: list[dict]
    anomalies: list[dict]       # ValidationAnomaly objects
    risk_level: str             # low | medium | high | critical

    # Compliance
    compliance_anomalies: list[dict]

    # Feedback loops
    critic_feedback: str | None
    human_feedback: dict | None  # From quarantine resume endpoint

    # Control
    status: str                 # processing | completed | quarantined | failed
    paused: bool
    pause_reason: str | None
    retry_count: int
    max_retries: int            # Default 3

    # Storage
    graph_updated: bool
    neo4j_id: str | None

    # Audit
    error_history: list[str]
    current_node: str
    processing_time_ms: int
```

---

## Anomaly Types

### `ValidationAnomaly`
Data quality issues detected during `validate_invoice`:
- Missing required fields
- Invalid date logic (due date before invoice date)
- Line item math errors (quantity × unit_price ≠ line_total)
- Total amount mismatch

### `ComplianceAnomaly`
Contract violations detected during `compliance_audit`:
- Retention rate not applied correctly
- Unit prices exceed contracted rates
- Invoice total exceeds billing cap
- Cost codes outside approved project scope

### Risk Levels
| Level | Action |
|-------|--------|
| `low` | Proceed to compliance check → insert |
| `medium` | Trigger critic loop, re-extract (up to 3 retries) |
| `high` | Quarantine for human review |
| `critical` | Quarantine immediately |

---

## Checkpointing & Quarantine

- State is checkpointed to SQLite at each node (`settings.workflow_checkpoint_db`)
- Quarantined documents are surfaced via `GET /api/workflows/quarantined`
- Human reviewers can correct and resume via `POST /api/workflows/{document_id}/resume`
- The workflow reloads the last checkpoint and continues from the quarantine node

---

## Neo4j Graph Structure

After successful processing, the graph contains:

```
(Invoice {invoice_number, date, total_amount, user_id, ...})
    ├── [:HAS_LINE_ITEM] ──→ (LineItem {description, quantity, unit_price, total})
    ├── [:ISSUED_BY] ──────→ (Contractor {name, contractor_id})
    └── [:BILLED_FOR] ─────→ (Project {name, project_id})
                                  └── [:GOVERNED_BY] ──→ (Contract {contract_id, ...})
```

All nodes include `user_id` for multi-tenant filtering.

---

## Adding Support for a New Document Type

1. Create `{type}_extractor.py` with a class that produces a Pydantic model
2. Add nodes in `pipeline/nodes.py` following the extract → validate → insert pattern
3. Create a new workflow file `pipeline/{type}_workflow.py` using `StateGraph`
4. Wire a new upload tool in `backend/agents/tools/{type}_upload_tool.py`
