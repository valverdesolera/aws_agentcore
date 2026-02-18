# Teilur Stock Agent

AI-powered financial analysis agent that combines **real-time stock data**, **historical price retrieval**, and **knowledge-base Q&A** through a [LangGraph](https://github.com/langchain-ai/langgraph) ReAct loop deployed on [AWS AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-core.html).

---

## Architecture Overview

```
User → Cognito Auth → AgentCore Runtime (BedrockAgentCoreApp)
                              │
                       LangGraph Agent
                        ┌─────┼─────┐
                        │     │     │
                   Real-time  Hist.  Document
                   Stock      Stock  Retrieval
                   Price      Price  (FAISS)
                        │     │     │
                        └─────┼─────┘
                              │
                          Langfuse
                        (Observability)
```

### Clean Architecture layers

| Layer | Key modules |
|---|---|
| **Domain** | `src/domain/entities/`, `src/domain/ports/` |
| **Application** | `src/application/use_cases/`, `src/application/agent/`, `src/application/services/` |
| **Infrastructure** | `src/infrastructure/` (adapters, entry points, auth, secrets) |

All source-code dependencies point **inward** — Infrastructure → Application → Domain. See [`docs/CleanArchitecture.md`](docs/CleanArchitecture.md) for the full audit.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | >= 3.10 |
| AWS CLI v2 | configured with deployment credentials |
| Terraform | >= 1.5 |
| Docker | optional — only needed for local container builds |
| [Langfuse](https://cloud.langfuse.com) | free-tier cloud account |
| [AgentCore Starter Toolkit](https://pypi.org/project/bedrock-agentcore-starter-toolkit/) | latest |

---

## Step-by-Step Deployment

### Step 1 — Clone the repository

```bash
git clone <repo-url>
cd teilur-stock-agent
```

### Step 2 — Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in:
#   COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_REGION
#   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
```

### Step 3 — Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn python-dotenv   # local dev extras
```

### Step 4 — Deploy cloud infrastructure with Terraform

```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```

Note the outputs — you will need them in later steps:

```bash
terraform output -raw cognito_user_pool_id
terraform output -raw cognito_user_pool_client_id
terraform output -raw ecr_repository_name
terraform output -raw agentcore_execution_role_arn
terraform output -raw langfuse_secret_arn
```

### Step 5 — Build the knowledge base

Downloads the three Amazon financial documents, chunks them, embeds them with Bedrock Titan, and persists the FAISS index to `vectorstore/`.

```bash
python -m src.infrastructure.knowledge_base.ingest
```

### Step 6 — Create a Cognito test user

```bash
POOL_ID=$(cd infrastructure && terraform output -raw cognito_user_pool_id)

aws cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" \
  --username testuser@example.com

aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" \
  --username testuser@example.com \
  --password "TestPassword123!" \
  --permanent
```

### Step 7 — Store Langfuse credentials in Secrets Manager

```bash
SECRET_ARN=$(cd infrastructure && terraform output -raw langfuse_secret_arn)

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_ARN" \
  --secret-string '{
    "LANGFUSE_PUBLIC_KEY": "<your-public-key>",
    "LANGFUSE_SECRET_KEY": "<your-secret-key>",
    "LANGFUSE_HOST": "https://cloud.langfuse.com"
  }'
```

### Step 8 — Configure and deploy to AgentCore

```bash
ROLE_ARN=$(cd infrastructure && terraform output -raw agentcore_execution_role_arn)
ECR_NAME=$(cd infrastructure && terraform output -raw ecr_repository_name)
POOL_ID=$(cd infrastructure && terraform output -raw cognito_user_pool_id)
CLIENT_ID=$(cd infrastructure && terraform output -raw cognito_user_pool_client_id)
SECRET_ARN=$(cd infrastructure && terraform output -raw langfuse_secret_arn)

pip install bedrock-agentcore-starter-toolkit

agentcore configure \
  --entrypoint src/infrastructure/entrypoints/agentcore_handler.py \
  --requirements-file requirements.txt \
  --execution-role "$ROLE_ARN" \
  --ecr "$ECR_NAME" \
  --authorizer-config '{"type":"COGNITO","userPoolId":"'"$POOL_ID"'","clientId":"'"$CLIENT_ID"'"}' \
  --request-header-allowlist "Authorization" \
  --non-interactive

agentcore deploy --env "LANGFUSE_SECRET_ARN=$SECRET_ARN"
```

The deploy command prints the **runtime endpoint URL** — copy it into `AGENT_ENDPOINT` in the UAT notebook.

---

## Running Locally (FastAPI)

For local development without AgentCore, use the FastAPI entry point:

```bash
uvicorn src.infrastructure.entrypoints.fastapi_app:app --reload --port 8000
```

The local server exposes:

- `POST /query` — accepts `{"prompt": "...", "session_id": "..."}` with a Cognito Bearer token, streams SSE.
- `GET /health` — returns `{"status": "ok"}`.

---

## How to Run the UAT Notebook

```bash
pip install jupyter httpx
jupyter notebook notebooks/demo.ipynb
```

1. **Open** `notebooks/demo.ipynb` in Jupyter.
2. All configuration values (Cognito pool/client IDs, agent endpoint, test credentials) are **pre-filled** — no edits required.
3. **Run all cells sequentially** (`Kernel → Restart & Run All`).
4. Each query cell streams the agent's response token-by-token.
5. Section 3 displays Langfuse traces programmatically (if env vars are set) or as embedded dashboard screenshots.

---

## Project Structure

```
.
├── README.md
├── requirements.txt            # AgentCore container dependencies
├── pyproject.toml
│
├── src/
│   ├── domain/
│   │   ├── entities/           # StockPrice, HistoricalPrices, DocumentChunk
│   │   └── ports/              # Abstract interfaces (IStockDataProvider, IVectorStore …)
│   ├── application/
│   │   ├── agent/              # LangGraph ReAct graph, AgentState, system prompt
│   │   ├── use_cases/          # GetRealtimePriceUseCase, RunAgentUseCase …
│   │   └── services/           # IngestDocumentsService
│   └── infrastructure/
│       ├── stock_data/         # YFinanceStockDataProvider
│       ├── knowledge_base/     # FAISSVectorStore, PDFDocumentLoader, ingest CLI
│       ├── llm/                # BedrockChatAdapter
│       ├── observability/      # LangfuseObservabilityHandler
│       ├── auth/               # CognitoTokenValidator
│       ├── secrets/            # SecretsManagerAdapter
│       └── entrypoints/        # fastapi_app.py, agentcore_handler.py, tool_registry.py
│
├── infrastructure/             # Terraform — cloud provisioning (outside src/)
│   ├── main.tf
│   ├── cognito.tf
│   ├── ecr.tf
│   ├── iam.tf
│   ├── secrets.tf
│   ├── variables.tf
│   └── outputs.tf
│
├── notebooks/
│   └── demo.ipynb              # UAT demonstration notebook (self-contained, pre-filled)
│
├── docs/
│   ├── CleanArchitecture.md    # Architectural audit and layer rules
│   ├── phases/                 # Phase-by-phase implementation plans
│   └── screenshots/            # Langfuse dashboard screenshots (embedded in notebook)
│
├── vectorstore/                # Pre-built FAISS index (built by ingest CLI)
└── data/
    └── pdfs/                   # Downloaded Amazon financial PDFs (git-ignored)
```

---

## Cleanup

```bash
# 1. Destroy the AgentCore runtime and ECR image (from the project root):
agentcore destroy --force --delete-ecr-repo

# 2. Destroy all Terraform-managed cloud resources:
cd infrastructure
terraform destroy
```

> **Note:** The ECR repository is configured with `force_delete = true` in Terraform, so `terraform destroy` will succeed even if images remain after `agentcore destroy`.
