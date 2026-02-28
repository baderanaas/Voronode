# Voronode — Azure Deployment (Terraform)

## Architecture Overview

```
Internet (HTTPS)
       │
       ▼
┌──────────────────────────────────────────────┐
│         Azure Container Apps                 │
│         (Shared Consumption Plan)            │
│                                              │
│  ┌────────────────┐   ┌──────────────────┐   │
│  │   frontend     │──►│    backend       │   │
│  │   Streamlit    │   │    FastAPI        │   │
│  │   port 8501    │   │    port 8080      │   │
│  │   external     │   │    internal only  │   │
│  └────────────────┘   └────────┬─────────┘   │
└───────────────────────────────-│─────────────┘
                                 │ public IPs
                    ┌────────────┴────────────┐
                    │                         │
           ┌────────▼──────┐        ┌─────────▼──────┐
           │  Neo4j ACI    │        │ ChromaDB ACI   │
           │  port 7687    │        │ port 8000      │
           │  (+ 7474 UI)  │        │                │
           └───────────────┘        └────────────────┘
                Azure Files (persistent volumes)
```

### Azure Services Used

| Service | Purpose |
|---------|---------|
| Azure Container Apps | Frontend (Streamlit) + Backend (FastAPI) — scales to zero when idle |
| Azure Container Instances | Neo4j + ChromaDB — always-on, persistent storage |
| Azure Container Registry | Docker image storage (backend, frontend, neo4j, chromadb) |
| Azure Storage Account | 3 file shares: neo4j-data, neo4j-logs, chroma-data |
| Azure Key Vault | API secrets — accessed by apps via managed identity |
| Azure Log Analytics | Centralised logs for Container Apps |
| Azure Application Insights | Request tracing and metrics |
| User-Assigned Managed Identity | Shared identity for ACR pull + Key Vault access |

---

## Prerequisites

```bash
# Azure CLI
az --version          # >= 2.50
az login

# Terraform
terraform -version    # >= 1.5

# Docker (for building and pushing images)
docker --version
```

---

## File Structure

```
terraform/
├── main.tf                   # Provider config + resource group
├── variables.tf              # All input variables with defaults
├── networking.tf             # (placeholder — VNet removed for student account)
├── acr.tf                    # Azure Container Registry + AcrPull role
├── storage.tf                # Storage account + 4 file shares
├── keyvault.tf               # Key Vault + managed identity + secrets
├── databases.tf              # Neo4j + ChromaDB container instances
├── apps.tf                   # Container Apps environment + backend + frontend
├── monitoring.tf             # Log Analytics + Application Insights
├── outputs.tf                # Useful values printed after apply
├── terraform.tfvars          # Your real secrets — GITIGNORED, never commit
├── terraform.tfvars.example  # Template to copy from — safe to commit
└── README.md                 # This file
```

---

## Deployment Steps

### Step 0 — Configure variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and fill in all API keys and secrets
```

Required values in `terraform.tfvars`:

| Variable | Description |
|----------|-------------|
| `groq_api_key` | Groq API key |
| `openai_api_key` | OpenAI API key |
| `gemini_api_key` | Google Gemini API key |
| `anthropic_api_key` | Anthropic API key |
| `tavily_api_key` | Tavily search key (leave `""` if unused) |
| `jwt_secret_key` | Random string for JWT signing |
| `neo4j_password` | Password for the Neo4j database |
| `neon_database_url` | Neon Postgres connection string (e.g. `postgresql://user:pass@ep-xxx.neon.tech/voronode?sslmode=require`) |
| `backend_image` | Fill in after Step 2 |
| `frontend_image` | Fill in after Step 2 |

---

### Step 1 — Bootstrap ACR

Create the resource group and container registry first so images can be pushed.

```bash
terraform init
terraform apply -target=azurerm_resource_group.main -target=azurerm_container_registry.main
```

Get the registry URL:

```bash
ACR=$(terraform output -raw acr_login_server)
echo $ACR   # e.g. voronodeacr2kdw.azurecr.io
```

---

### Step 2 — Build and push all images

Log in to ACR:

```bash
az acr login --name $(echo $ACR | cut -d'.' -f1)
```

Build and push the app images:

```bash
# From the project root (one level above terraform/)
cd ..

docker build -f docker/Dockerfile.backend -t $ACR/backend:latest .
docker push $ACR/backend:latest

docker build -f docker/Dockerfile.frontend -t $ACR/frontend:latest .
docker push $ACR/frontend:latest
```

Mirror Neo4j and ChromaDB into ACR (avoids Docker Hub rate limits):

```bash
docker pull neo4j:5.18
docker tag neo4j:5.18 $ACR/neo4j:5.18
docker push $ACR/neo4j:5.18

docker pull chromadb/chroma:latest
docker tag chromadb/chroma:latest $ACR/chromadb:latest
docker push $ACR/chromadb:latest
```

Update `terraform.tfvars` with the image URIs:

```hcl
backend_image  = "voronodeacrXXXX.azurecr.io/backend:latest"
frontend_image = "voronodeacrXXXX.azurecr.io/frontend:latest"
```

---

### Step 3 — Deploy everything

```bash
cd terraform
terraform apply
```

This creates (in dependency order):
1. Storage account + file shares
2. Managed identity + Key Vault + secrets
3. Log Analytics + Application Insights
4. Neo4j + ChromaDB container instances (with persistent Azure Files volumes)
5. Container Apps environment
6. Backend Container App (internal ingress, `DATABASE_URL` wired from Key Vault)
7. Frontend Container App (public HTTPS ingress)

---

### Step 4 — Verify

```bash
# Get the public frontend URL
terraform output frontend_url

# Check the Streamlit health endpoint
curl "$(terraform output -raw frontend_url)/_stcore/health"
```

---

## Useful Commands

```bash
# See all outputs
terraform output

# Re-deploy after a code change (push new image first)
docker build -f docker/Dockerfile.backend -t $ACR/backend:latest . && docker push $ACR/backend:latest
terraform apply   # updates the Container App revision

# View live logs
az containerapp logs show --name ca-backend-voronode --resource-group rg-voronode-dev --follow
az containerapp logs show --name ca-frontend-voronode --resource-group rg-voronode-dev --follow

# Tear down everything
terraform destroy
```

---

## Pausing and Resuming (without destroying)

### Pause — stop all running services

Container Apps scale to zero automatically when idle (`min-replicas=0`) — no action needed.
The only services that cost money while idle are the ACIs:

```bash
az container stop --name aci-neo4j-voronode --resource-group rg-voronode-dev
az container stop --name aci-chromadb-voronode --resource-group rg-voronode-dev
```

### Resume — bring everything back up

```bash
az container start --name aci-neo4j-voronode --resource-group rg-voronode-dev
az container start --name aci-chromadb-voronode --resource-group rg-voronode-dev

az containerapp update --name ca-backend-voronode --resource-group rg-voronode-dev \
    --set-env-vars \
      "NEO4J_URI=bolt://neo4j-voronode.westeurope.azurecontainer.io:7687" \
      "CHROMADB_HOST=chromadb-voronode.westeurope.azurecontainer.io"
```

ACI containers get new public IPs on each restart — the `containerapp update` repoints the backend using stable FQDNs. Container Apps spin up automatically on the next incoming request.

### Update a secret (e.g. rotate an API key)

1. Update the value in `terraform.tfvars`
2. Run `terraform apply` — updates Key Vault and the Container App secret
3. Force a new revision to pick up the change:

```bash
az containerapp update --name ca-backend-voronode --resource-group rg-voronode-dev --image voronodeacreina.azurecr.io/backend:latest
```

---


## Local Development vs Azure

`docker/docker-compose.yml` is **not used in this deployment**. It exists only for local development — it starts Neo4j and ChromaDB on your machine so you can run the backend and frontend locally without Azure:

```bash
docker compose -f docker/docker-compose.yml up -d
uv run uvicorn backend.api.main:app --reload
streamlit run frontend/app.py
```

In Azure, Neo4j and ChromaDB are replaced by the Container Instances in `databases.tf`. The Dockerfiles (`docker/Dockerfile.backend`, `docker/Dockerfile.frontend`) are used for the Azure deployment.

---

## Notes

- **Region**: `westeurope` (Netherlands). Germany West Central is not available on Azure for Students.
- **Container Apps** use the shared consumption plan (no VNet) — scales to zero when idle.
- **Neo4j and ChromaDB** run as Container Instances with public IPs. The backend reaches them via their IPs, which Terraform injects as environment variables at deploy time.
- **Secrets** are stored in Key Vault and referenced by the backend Container App via managed identity — they never appear in plain text in the Container App config.
- **Postgres** (Neon) is used for all structured state: users, conversations, messages, workflow states, and LangGraph checkpoints. The connection string is stored in Key Vault and injected as `DATABASE_URL`. Data persists across container restarts.
- If ACI IPs change after a redeploy, run `terraform apply` to update the backend env vars automatically.
