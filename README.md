# Voronode - Autonomous Financial Risk & Compliance System

AI-powered multi-agent system for construction financial oversight using GraphRAG.

## Architecture

- **Knowledge Graph:** Neo4j (relationships between projects, invoices, contracts)
- **Vector Store:** ChromaDB (unstructured document search)
- **LLM:** Groq (llama3.3 for reasoning and extraction)
- **Orchestration:** LangGraph (multi-agent workflows)

## Phase 1: Knowledge Foundation ✅

Current implementation:
- Graph schema defined (Projects, Invoices, Contractors, etc.)
- Database infrastructure (Neo4j + ChromaDB via Docker)
- Core Pydantic models with validation
- Synthetic test data generation
- Database client wrappers

## Setup

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Groq API key

### Installation

1. Clone and enter directory:
```bash
cd voronode
```

2. Create `.env` file:
```bash
cp .env.example .env
# Add your GROQ_API_KEY
```

3. Install dependencies:
```bash
uv sync
```

4. Start databases:
```bash
cd docker
docker-compose up -d
```

5. Initialize schemas:
```bash
uv run python scripts/setup_neo4j.py
uv run python scripts/setup_chromadb.py
```

6. Generate test data:
```bash
uv run python scripts/generate_test_data.py
```

### Verify Setup

```bash
# Run tests
uv run pytest

# Check Neo4j: http://localhost:7474
# User: neo4j, Password: voronode123

# Check ChromaDB: http://localhost:8000/api/v1/heartbeat
```

## Project Structure

```
voronode/
├── backend/
│   ├── core/          # Config, models, state definitions
│   ├── graph/         # Neo4j client & schema
│   ├── vector/        # ChromaDB client
│   └── tests/         # Unit & integration tests
├── scripts/           # Setup & data generation
├── docker/            # Database containers
└── main.py           # Entry point
```

## Next Steps (Phase 2)

- Build Document Intelligence Agent (PDF → JSON extraction with Groq)
- Implement Graph Builder (JSON → Neo4j insertion)
- Create FastAPI endpoints for document upload

## License

See LICENSE file.
