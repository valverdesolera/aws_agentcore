# Phase 7 — UAT Notebook & Documentation

## Summary

Produce the final deliverables: a Jupyter notebook that demonstrates end-to-end functionality (authentication, querying, streaming, observability) and a README with clear deployment instructions. This phase validates that all acceptance criteria are met and that the solution is reproducible by the review team.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `jupyter` or `jupyterlab` | Notebook runtime |
| `boto3` | Cognito authentication from notebook |
| `httpx` | Async HTTP client for calling the endpoint (with streaming support) |
| `langfuse` | For programmatic trace retrieval (optional) |
| All prior phases | Fully deployed and operational |

---

## Setup

### 1. Install Notebook Dependencies

```bash
pip install jupyter httpx boto3 langfuse
```

### 2. File Structure

```
.
├── README.md                  # Deployment documentation
├── notebooks/
│   └── demo.ipynb             # UAT demonstration notebook
├── docs/
│   └── phases/                # Phase documentation (this folder)
├── infrastructure/            # Terraform files
├── src/                       # Application source code
└── requirements.txt           # Project dependencies
```

---

## Requirements

### A. Jupyter Notebook Structure

The notebook must contain the following sections in order:

#### Section 1: Setup & Configuration

```python
# Cell 1: Imports and Configuration
import boto3
import httpx
import json
import os

# Configuration — pre-filled with live deployment values (reviewer does not need to change these)
COGNITO_USER_POOL_ID = "<filled after terraform apply>"
COGNITO_CLIENT_ID = "<filled after terraform apply>"
COGNITO_REGION = "us-east-1"
AGENT_ENDPOINT = "<filled after agentcore deploy>"

# Cognito test user credentials
USERNAME = "testuser@example.com"
PASSWORD = "TestPassword123!"
```

#### Section 2: Cognito User Authentication

This section must demonstrate authenticating against the Cognito user pool.

```python
# Cell 2: Authenticate with Cognito
cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

auth_response = cognito_client.initiate_auth(
    ClientId=COGNITO_CLIENT_ID,
    AuthFlow="USER_PASSWORD_AUTH",
    AuthParameters={
        "USERNAME": USERNAME,
        "PASSWORD": PASSWORD,
    },
)

id_token = auth_response["AuthenticationResult"]["IdToken"]
access_token = auth_response["AuthenticationResult"]["AccessToken"]

print(f"Authentication successful!")
print(f"ID Token (first 50 chars): {id_token[:50]}...")
print(f"Access Token (first 50 chars): {access_token[:50]}...")
```

#### Section 3: UAT Queries (5 Required)

Each query must be in its own cell with the streaming response displayed.

```python
# Cell 3: Helper function for streaming queries
#
# NOTE: The AgentCore endpoint uses "prompt" as the payload key and streams
# responses as line-delimited JSON (not SSE). If your endpoint uses FastAPI's
# SSE format (data: {json}\n\n), adjust the parsing accordingly.

async def query_agent(query: str, token: str, session_id: str = None):
    """Send a query to the agent endpoint and display streamed response.

    Works with the AgentCore endpoint which expects {"prompt": "..."} payloads
    and validates the Bearer token via the configured Cognito authorizer.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": query,
        "session_id": session_id,
    }

    print(f"Query: {query}")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            AGENT_ENDPOINT,
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                # Handle both SSE format (data: {...}) and line-delimited JSON
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                else:
                    data = line
                try:
                    event = json.loads(data)
                    if event.get("content"):
                        print(event["content"])
                except json.JSONDecodeError:
                    print(line)

    print("\n" + "=" * 60)
```

**Query 1:**
```python
await query_agent("What is the stock price for Amazon right now?", id_token, "session-q1")
```

**Query 2:**
```python
await query_agent("What were the stock prices for Amazon in Q4 last year?", id_token, "session-q2")
```

**Query 3:**
```python
await query_agent(
    "Compare Amazon's recent stock performance to what analysts predicted in their reports",
    id_token,
    "session-q3",
)
```

**Query 4:**
```python
await query_agent(
    "I'm researching AMZN give me the current price and any relevant information about their AI business",
    id_token,
    "session-q4",
)
```

**Query 5:**
```python
await query_agent(
    "What is the total amount of office space Amazon owned in North America in 2024?",
    id_token,
    "session-q5",
)
```

#### Section 4: Langfuse Traces

Show Langfuse traces as evidence of observability. Two approaches:

**Option A: Programmatic trace retrieval**
```python
from langfuse import get_client

langfuse = get_client()

# Fetch recent traces
traces = langfuse.fetch_traces(limit=5)
for trace in traces.data:
    print(f"Trace ID: {trace.id}")
    print(f"  Name: {trace.name}")
    print(f"  Latency: {trace.latency}s")
    print(f"  Input: {str(trace.input)[:100]}...")
    print(f"  Output: {str(trace.output)[:100]}...")
    print()
```

**Option B: Screenshots**
Include screenshots from the Langfuse dashboard showing:
- Trace timeline for at least one query
- LLM call details (input/output, token usage)
- Tool call details (tool name, arguments, result)

```python
# Display embedded screenshots
from IPython.display import Image, display

display(Image(filename="docs/screenshots/langfuse_trace_overview.png"))
display(Image(filename="docs/screenshots/langfuse_trace_detail.png"))
```

---

### B. README Documentation

The README must cover:

#### 1. Architecture Overview

Brief description of the system architecture with a diagram (text or image):

```
User → Cognito Auth → FastAPI (AgentCore Runtime)
                          │
                    LangGraph Agent
                     ┌────┼────┐
                     │    │    │
              Real-time  Hist.  Document
              Stock     Stock   Retrieval
              Price     Price   (FAISS)
                     │    │    │
                     └────┼────┘
                          │
                      Langfuse
                    (Observability)
```

#### 2. Prerequisites

- AWS Account with appropriate permissions
- AWS CLI v2 configured
- Terraform >= 1.5
- Python >= 3.10
- Docker (optional, for local container builds)
- Langfuse cloud account (free tier)

#### 3. Step-by-Step Deployment

```markdown
### Step 1: Clone the Repository
git clone <repo-url>
cd teilur-stock-agent

### Step 2: Configure Environment Variables
cp .env.example .env
# Edit .env with your values

### Step 3: Deploy Infrastructure with Terraform
cd infrastructure
terraform init
terraform plan
terraform apply

### Step 4: Build the Knowledge Base
python -m src.knowledge_base.ingest

### Step 5: Deploy to AgentCore
pip install bedrock-agentcore-starter-toolkit
agentcore configure \
  --entrypoint src/agent_handler.py \
  --execution-role $(terraform output -raw agentcore_execution_role_arn) \
  --ecr $(terraform output -raw ecr_repository_name) \
  --authorizer-config '{"type":"COGNITO","userPoolId":"'$(terraform output -raw cognito_user_pool_id)'","clientId":"'$(terraform output -raw cognito_user_pool_client_id)'"}' \
  --request-header-allowlist "Authorization" \
  --non-interactive
agentcore deploy \
  --env LANGFUSE_SECRET_ARN=$(terraform output -raw langfuse_secret_arn)

### Step 6: Create a Test User in Cognito
aws cognito-idp admin-create-user \
  --user-pool-id $(terraform output -raw cognito_user_pool_id) \
  --username testuser@example.com

aws cognito-idp admin-set-user-password \
  --user-pool-id $(terraform output -raw cognito_user_pool_id) \
  --username testuser@example.com \
  --password "TestPassword123!" \
  --permanent

### Step 7: Run the Demo Notebook
jupyter notebook notebooks/demo.ipynb
```

#### 4. How to Run the UAT Notebook

- Open `notebooks/demo.ipynb` in Jupyter
- Update the configuration cell with Terraform output values
- Run all cells sequentially
- Each query cell shows the streamed agent response
- The Langfuse section shows observability traces

#### 5. Cleanup

```markdown
### Destroy Resources

# From the project root (where .bedrock_agentcore.yaml is):
agentcore destroy --force --delete-ecr-repo

# Then destroy Terraform infrastructure (ECR has force_delete=true):
cd infrastructure
terraform destroy
```

---

## Implementation Notes

1. **Notebook must be executable.** The review team will run it. Ensure:
   - All configuration is in one clearly marked cell at the top
   - No hardcoded secrets (use environment variables or clearly labeled placeholders)
   - Each cell is independent (can be re-run without side effects)
   - Output is preserved from a successful run (so reviewers can see expected results)

2. **Cognito authentication demo.** The notebook must visually show:
   - The `initiate_auth` call succeeding
   - The JWT token being obtained
   - The token being passed in the Authorization header

3. **Langfuse evidence.** Include both:
   - Screenshots embedded in the notebook (reliable, doesn't need reviewer's Langfuse access)
   - Optional programmatic trace retrieval (shows technical depth)

4. **Error handling in notebook.** Add try/except blocks around API calls with helpful error messages (e.g., "If you see 401, check that the Cognito user was created and the password is correct").

5. **Streaming client.** Use `httpx` with `aiter_lines()` for async streaming. The `query_agent` helper in section A handles both SSE format (`data: {...}`) and line-delimited JSON, so it works regardless of which endpoint format is used.

---

## Final Acceptance Criteria Checklist

- [ ] Repository has clear README with deployment instructions
- [ ] Notebook authenticates against Cognito user pool
- [ ] Notebook demonstrates all 5 UAT queries with streamed responses:
  - [ ] "What is the stock price for Amazon right now?"
  - [ ] "What were the stock prices for Amazon in Q4 last year?"
  - [ ] "Compare Amazon's recent stock performance to what analysts predicted in their reports"
  - [ ] "I'm researching AMZN give me the current price and any relevant information about their AI business"
  - [ ] "What is the total amount of office space Amazon owned in North America in 2024?"
- [ ] Notebook contains screenshots or API responses showing Langfuse traces
- [ ] Notebook shows user authentication from Cognito user pool
- [ ] All infrastructure is defined in Terraform
- [ ] Agent uses LangGraph with ReAct pattern
- [ ] Responses are streamed via `.astream()`
- [ ] Minimum 2 finance tools use yfinance
- [ ] Knowledge base includes all 3 Amazon financial documents
