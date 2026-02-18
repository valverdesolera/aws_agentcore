"""
FastAPI entry point — local development server.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.

This module is the Composition Root for local runs: it wires all infrastructure
adapters and passes them to the application layer.  Authentication is performed
by CognitoTokenValidator (ITokenValidator) reading the Bearer JWT from each request.

Run locally:
    uvicorn src.infrastructure.entrypoints.fastapi_app:app --reload --port 8000
"""

import json
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from src.application.agent.graph import build_agent_graph
from src.application.use_cases.run_agent import RunAgentUseCase
from src.infrastructure.auth.cognito_validator import CognitoTokenValidator
from src.infrastructure.entrypoints.tool_registry import create_tools
from src.infrastructure.knowledge_base.faiss_vector_store import FAISSVectorStore
from src.infrastructure.llm.bedrock_adapter import BedrockChatAdapter
from src.infrastructure.observability.langfuse_adapter import LangfuseObservabilityHandler
from src.infrastructure.stock_data.yfinance_adapter import YFinanceStockDataProvider

# ---------------------------------------------------------------------------
# Composition Root — wire all dependencies once at startup
# ---------------------------------------------------------------------------
_stock_provider = YFinanceStockDataProvider()
_vector_store = FAISSVectorStore.load("vectorstore")
_llm = BedrockChatAdapter()
_observability = LangfuseObservabilityHandler()
_tools = create_tools(_stock_provider, _vector_store)
_graph = build_agent_graph(_llm, _tools)
_run_use_case = RunAgentUseCase(_graph, _observability)

_validator = CognitoTokenValidator(
    user_pool_id=os.environ["COGNITO_USER_POOL_ID"],
    client_id=os.environ["COGNITO_CLIENT_ID"],
    region=os.environ.get("COGNITO_REGION", "us-east-1"),
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Teilur Stock Agent API")


class QueryRequest(BaseModel):
    prompt: str
    session_id: str | None = None


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: validate the Cognito JWT from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = auth_header.split(" ", 1)[1]
    try:
        return _validator.validate(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/query")
async def query_agent(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
):
    """Stream the agent's response as Server-Sent Events."""

    async def event_stream():
        async for event in _run_use_case.execute(
            query=body.prompt,
            user_id=user.get("sub"),
            session_id=body.session_id,
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
