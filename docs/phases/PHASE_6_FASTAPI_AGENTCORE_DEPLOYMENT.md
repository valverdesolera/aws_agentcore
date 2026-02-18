# Phase 6 — FastAPI Endpoint & AgentCore Deployment

> **Architecture reference:** Before writing or reviewing any code for this phase, consult
> [`docs/CleanArchitecture.md`](../CleanArchitecture.md).
> Key files for this phase:
> - **Domain:** `src/domain/ports/token_validator_port.py`, `src/domain/ports/secret_store_port.py`
> - **Infrastructure / Entrypoints:** `src/infrastructure/auth/cognito_validator.py`, `src/infrastructure/secrets/secrets_manager_adapter.py`, `src/infrastructure/observability/langfuse_adapter.py`, `src/infrastructure/entrypoints/fastapi_app.py`, `src/infrastructure/entrypoints/agentcore_handler.py`

## Summary

Wrap the LangGraph agent in a FastAPI application with a streaming endpoint, add Cognito JWT validation middleware, containerize the application, and deploy it to AWS AgentCore Runtime. This is the integration phase that ties together all previous phases into a live, secured, streaming API.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `fastapi` | Latest |
| `uvicorn` | ASGI server for local testing |
| `bedrock-agentcore` | AgentCore Runtime SDK |
| `bedrock-agentcore-starter-toolkit` | AgentCore CLI for deployment |
| `python-jose[cryptography]` or `pyjwt` | JWT token validation |
| `httpx` | Async HTTP client for JWKS fetching |
| Docker or Finch | Container building (local build option) |
| Phase 1 | Cognito pool ID, ECR repo URL, IAM role ARN |
| Phase 4 | Compiled LangGraph agent graph |
| Phase 5 | Langfuse callback handler |

---

## Setup

### 1. Install Dependencies

```bash
pip install fastapi uvicorn bedrock-agentcore bedrock-agentcore-starter-toolkit python-jose[cryptography] httpx
```

### 2. Project File Structure

```
src/
├── app.py                 # FastAPI application (non-AgentCore local dev)
├── agent_handler.py       # AgentCore entrypoint wrapper
├── auth/
│   ├── __init__.py
│   └── cognito.py         # Cognito JWT validation middleware
├── agent/
│   └── graph.py           # From Phase 4
├── tools/
│   └── stock_tools.py     # From Phase 2
├── knowledge_base/
│   └── retriever.py       # From Phase 3
├── requirements.txt       # All dependencies for AgentCore deployment
└── Dockerfile             # Optional, for container deployment
```

---

## Requirements

### A. Cognito JWT Validation

Validate the `Authorization: Bearer <token>` header against the Cognito user pool.

```python
# auth/cognito.py
import os
import httpx
from jose import jwt, JWTError
from functools import lru_cache


COGNITO_REGION = os.environ.get("COGNITO_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]

JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"


@lru_cache()
def get_jwks() -> dict:
    """Fetch and cache the JWKS from Cognito."""
    response = httpx.get(JWKS_URL)
    response.raise_for_status()
    return response.json()


def validate_cognito_token(token: str) -> dict:
    """Validate a Cognito JWT token and return the claims.

    Raises:
        JWTError: If token is invalid, expired, or malformed.
    """
    jwks = get_jwks()

    # Decode header to find the signing key
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    # Find the matching key in JWKS
    rsa_key = None
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            rsa_key = key
            break

    if not rsa_key:
        raise JWTError("Unable to find matching key in JWKS")

    # Verify and decode the token
    claims = jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=COGNITO_CLIENT_ID,
        issuer=ISSUER,
    )

    # Verify token_use claim — ensure we received an ID token, not an access token.
    # Cognito ID tokens have an `aud` claim (= app client ID) and `token_use: "id"`.
    # Cognito access tokens do NOT have `aud` — they use `client_id` instead.
    # The jwt.decode() with `audience=` above would already reject access tokens
    # (since they lack `aud`), but this explicit check provides a clearer error message.
    token_use = claims.get("token_use")
    if token_use != "id":
        raise JWTError(f"Invalid token_use: expected 'id', got '{token_use}'")

    return claims
```

**Reference:**
- AWS Cognito JWT verification: https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html

---

### B. FastAPI Application (Local Development)

For local development and testing before AgentCore deployment:

```python
# app.py
import json
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler

from src.agent.graph import graph
from src.auth.cognito import validate_cognito_token


app = FastAPI(title="Teilur Stock Agent API")


class QueryRequest(BaseModel):
    query: str
    session_id: str = None


async def get_current_user(request: Request) -> dict:
    """Dependency that validates the Cognito JWT from the Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]
    try:
        claims = validate_cognito_token(token)
        return claims
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


@app.post("/query")
async def query_agent(
    request: QueryRequest,
    user: dict = Depends(get_current_user),
):
    """Stream agent response for a user query."""
    langfuse_handler = CallbackHandler()

    # Langfuse v3: pass user/session context via config metadata
    config = {
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_user_id": user.get("sub"),
            "langfuse_session_id": request.session_id,
            "langfuse_tags": ["api-request"],
        },
        "recursion_limit": 10,
    }

    async def event_stream():
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content=request.query)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                last_msg = update["messages"][-1]
                event_data = {
                    "node": node_name,
                    "content": last_msg.content if hasattr(last_msg, "content") else str(last_msg),
                    "type": last_msg.__class__.__name__,
                }
                yield f"data: {json.dumps(event_data)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**FastAPI StreamingResponse reference:**
- SSE format: `data: {json}\n\n` for each event
- `media_type="text/event-stream"` for Server-Sent Events
- Async generator yields chunks as the agent produces them
- Reference: https://fastapi.tiangolo.com/advanced/custom-response/

---

### C. AgentCore Runtime Wrapper

For deployment to AgentCore Runtime, wrap the agent in the `BedrockAgentCoreApp` pattern:

```python
# agent_handler.py
import os
import json
import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_core.messages import HumanMessage

# --- Langfuse secrets bootstrap (must run before importing langfuse) ---
def _load_langfuse_secrets():
    """Fetch Langfuse API keys from Secrets Manager and inject into env."""
    secret_arn = os.environ.get("LANGFUSE_SECRET_ARN")
    if not secret_arn:
        return  # Local dev: already set via .env / python-dotenv

    sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    response = sm.get_secret_value(SecretId=secret_arn)
    secrets = json.loads(response["SecretString"])

    os.environ["LANGFUSE_SECRET_KEY"] = secrets["LANGFUSE_SECRET_KEY"]
    os.environ["LANGFUSE_PUBLIC_KEY"] = secrets["LANGFUSE_PUBLIC_KEY"]
    os.environ["LANGFUSE_BASE_URL"]   = secrets["LANGFUSE_BASE_URL"]

_load_langfuse_secrets()  # Must run before any `from langfuse import ...`

from langfuse.langchain import CallbackHandler  # noqa: E402 — import after env vars are set
from src.agent.graph import graph  # noqa: E402

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    """AgentCore entrypoint — streams agent responses.

    When an OAuth authorizer is configured (see Deployment Steps), AgentCore validates
    the Bearer token BEFORE this function is called. The validated user info is available
    in context (if provided by the authorizer). The payload contains the request body.
    """
    query = payload.get("prompt", "Hello!")
    session_id = payload.get("session_id")

    # Extract user_id from the request context if available.
    # The context is a RequestContext object with fields: session_id, request_headers, request.
    # When an OAuth authorizer is configured, AgentCore validates the JWT before this handler
    # is called, but the decoded claims are NOT automatically parsed into a structured object.
    # The Authorization header is available via context.request_headers.
    user_id = None
    if context and context.request_headers:
        auth_header = context.request_headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                import json, base64
                # Decode the JWT payload (second segment) to extract the 'sub' claim.
                # Signature is already validated by AgentCore's authorizer.
                token = auth_header.split(" ", 1)[1]
                payload_b64 = token.split(".")[1]
                # Add padding if needed
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                token_payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                user_id = token_payload.get("sub")
            except Exception:
                pass  # Proceed without user_id if decoding fails

    langfuse_handler = CallbackHandler()

    # Langfuse v3: pass user/session context via config metadata
    config = {
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_user_id": user_id,
            "langfuse_session_id": session_id,
            "langfuse_tags": ["agentcore"],
        },
        "recursion_limit": 10,
    }

    # Stream results back
    async for chunk in graph.astream(
        {"messages": [HumanMessage(content=query)]},
        config=config,
        stream_mode="updates",
    ):
        for node_name, update in chunk.items():
            last_msg = update["messages"][-1]
            yield {
                "node": node_name,
                "content": last_msg.content if hasattr(last_msg, "content") else str(last_msg),
                "type": last_msg.__class__.__name__,
            }


if __name__ == "__main__":
    app.run()
```

**AgentCore required patterns:**
1. `from bedrock_agentcore.runtime import BedrockAgentCoreApp` — import the SDK (this is the only supported import path)
2. `app = BedrockAgentCoreApp()` — initialize
3. `@app.entrypoint` — decorate the handler function (the second parameter **must** be named exactly `context` for the framework to pass it)
4. `app.run()` — let AgentCore control execution (starts a uvicorn server on port 8080)
5. The entrypoint can be `async` and use `yield` for streaming — the framework auto-wraps yielded dicts as SSE events (`data: {json}\n\n`)

**Reference:** https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/overview.html

---

### D. Requirements File

```
# requirements.txt — used by AgentCore for cloud deployment
bedrock-agentcore
langchain-aws
langchain-core
langchain-community
langchain-text-splitters
langgraph
faiss-cpu
pypdf
yfinance
langfuse
python-jose[cryptography]
httpx
boto3
```

For local development with `app.py` (FastAPI), also install:
```bash
pip install fastapi uvicorn
```
These are NOT needed in the AgentCore `requirements.txt` because AgentCore handles HTTP serving.

---

### E. Deployment Steps

```bash
# 1. Install the AgentCore CLI
pip install bedrock-agentcore-starter-toolkit

# 2. Configure the agent (includes Cognito OAuth authorizer for JWT validation)
#    The --ecr flag expects a repository NAME, not a full URL.
#    The --authorizer-config enables AgentCore to validate Cognito JWTs before
#    the request reaches the @app.entrypoint handler.
agentcore configure \
  --entrypoint src/agent_handler.py \
  --execution-role <ROLE_ARN_FROM_TERRAFORM> \
  --ecr <ECR_REPO_NAME_FROM_TERRAFORM> \
  --authorizer-config '{"type":"COGNITO","userPoolId":"<POOL_ID>","clientId":"<CLIENT_ID>"}' \
  --request-header-allowlist "Authorization" \
  --non-interactive

# 3. Deploy to AWS (note: the command is `agentcore deploy`, not `agentcore launch`)
#    Langfuse keys are NOT passed here — they are fetched from Secrets Manager at runtime.
#    Only the secret ARN (non-sensitive) is passed as an env var via --env.
#    Cognito auth is handled by the authorizer (configured in step 2), NOT by env vars.
agentcore deploy \
  --env LANGFUSE_SECRET_ARN=<LANGFUSE_SECRET_ARN_FROM_TERRAFORM_OUTPUT>

# 4. Test the deployed agent (--bearer-token passes the Cognito JWT)
agentcore invoke '{"prompt": "What is the stock price for Amazon right now?"}' \
  --session-id "test-session-001" \
  --bearer-token "<COGNITO_ID_TOKEN>"

# 5. Check status
agentcore status --verbose
```

> **Authentication flow:** When `--authorizer-config` is set to `COGNITO`, AgentCore validates the Bearer JWT in the `Authorization` header **before** the request reaches `@app.entrypoint`. Invalid or missing tokens are rejected with 401. The `--request-header-allowlist "Authorization"` ensures the header is forwarded to AgentCore and is accessible via `context.request_headers` in the handler. For testing with `agentcore invoke`, use `--bearer-token` to pass a valid Cognito ID token. The exact JSON schema for `--authorizer-config` should be verified against the CLI at deploy time.

**AgentCore CLI reference:** https://aws.github.io/bedrock-agentcore-starter-toolkit/api-reference/cli.html

---

### F. Local Testing (Before Deployment)

```bash
# Option 1: Run FastAPI locally (uses Cognito JWT validation via middleware)
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload

# Test with curl (note: FastAPI uses "query" key, not "prompt")
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <COGNITO_ID_TOKEN>" \
  -d '{"query": "What is the stock price for Amazon right now?"}'

# Option 2: Run AgentCore handler locally (builds and runs in a container)
agentcore deploy --local

# Test locally (note: AgentCore uses "prompt" key)
agentcore invoke '{"prompt": "What is the stock price for Amazon right now?"}' --local
```

> **Payload format difference:** The FastAPI `app.py` expects `{"query": "..."}` while the AgentCore `agent_handler.py` expects `{"prompt": "..."}`. These are two separate entry points — `app.py` for local dev with uvicorn and `agent_handler.py` for cloud deployment via `agentcore deploy`. The Phase 7 notebook targets the AgentCore endpoint and uses `{"prompt": "..."}`. Consider unifying on one key if this causes confusion during development.

---

## Implementation Notes

1. **Secrets Manager bootstrap.** The `_load_langfuse_secrets()` function in section C above fetches Langfuse credentials from AWS Secrets Manager and injects them as environment variables **before** the `langfuse` import runs. This is critical — the Langfuse SDK reads `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_BASE_URL` from the environment at import time. The function uses `AWS_REGION` (the standard env var set by AgentCore Runtime), falling back to `us-east-1`. The IAM execution role created in Phase 1 (`iam.tf`) already grants `secretsmanager:GetSecretValue` on this specific secret ARN. No additional permissions are needed.

2. **Two entry points.** The project has two entry points:
   - `app.py` — standard FastAPI for local dev (runs with uvicorn). Validates Cognito JWTs via middleware. Expects `{"query": "..."}` payload.
   - `agent_handler.py` — AgentCore wrapper for cloud deployment. Auth handled by AgentCore's authorizer. Expects `{"prompt": "..."}` payload.
   Both share the same agent graph, tools, and Langfuse integration.

3. **AgentCore handles HTTP and auth.** When deployed to AgentCore Runtime, the SDK handles the HTTP server (uvicorn on port 8080), request routing, container lifecycle, **and JWT validation** (when `--authorizer-config` is set during `agentcore configure`). The `@app.entrypoint` function receives the parsed JSON payload directly — auth has already been validated by the time the handler is called. The handler receives requests at `POST /invocations`. The `context` parameter (a `RequestContext` object) provides `session_id`, `request_headers`, and the raw `request` object.

4. **Environment variables.** Langfuse keys are fetched from Secrets Manager at runtime (see note 1 above). Cognito auth is configured via `--authorizer-config` at configure time, NOT via `--env` flags. Never hardcode secrets.

5. **FAISS index in the container.** The pre-built FAISS vectorstore must be included in the container or downloaded at startup. Options:
   - Include `vectorstore/` directory in the deployment package
   - Download from S3 at startup
   - Build the index during container initialization (slower startup)

6. **Cold start.** AgentCore Runtime instances may have cold starts. Loading the FAISS index and initializing the LLM client adds to startup time. Consider keeping the index small and using lazy initialization.

---

## Verification Checklist

- [ ] FastAPI local server starts and `/health` returns 200
- [ ] `/query` rejects requests without Authorization header (401)
- [ ] `/query` rejects requests with invalid JWT (401)
- [ ] `/query` rejects access tokens (only ID tokens accepted, via `token_use` check)
- [ ] `/query` with valid ID token streams SSE events
- [ ] AgentCore handler deploys successfully (`agentcore deploy`)
- [ ] `agentcore invoke --bearer-token <VALID_TOKEN>` returns streamed results
- [ ] `agentcore invoke` without `--bearer-token` is rejected (401) when authorizer is configured
- [ ] Langfuse traces appear for deployed invocations
- [ ] `agentcore status` shows the agent as active
