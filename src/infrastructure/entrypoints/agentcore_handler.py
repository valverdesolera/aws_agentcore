"""
AgentCore Runtime entry point — cloud deployment.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.

Langfuse secrets are fetched from AWS Secrets Manager at container startup
(before any Langfuse import) so LANGFUSE_* env vars are available process-wide.
Authentication is handled by AgentCore's built-in OAuth authorizer; the validated
JWT is forwarded in context.request_headers so we can extract the user sub for
Langfuse tracing without re-validating the signature.

Deploy:
    agentcore configure \\
        --entrypoint src/infrastructure/entrypoints/agentcore_handler.py \\
        --requirements-file requirements.txt \\
        --execution-role <AGENTCORE_EXECUTION_ROLE_ARN> \\
        --ecr-uri <ECR_REPOSITORY_URL> \\
        --authorizer-config cognito \\
        --cognito-user-pool-id <COGNITO_USER_POOL_ID> \\
        --cognito-client-id <COGNITO_CLIENT_ID>
    agentcore deploy --env LANGFUSE_SECRET_ARN=<arn>
"""

import base64
import json
import os

# ---------------------------------------------------------------------------
# Secret bootstrap — must run before any library that reads LANGFUSE_* env vars
# ---------------------------------------------------------------------------
_secret_arn = os.environ.get("LANGFUSE_SECRET_ARN")
if _secret_arn:
    from src.infrastructure.secrets.secrets_manager_adapter import SecretsManagerAdapter
    SecretsManagerAdapter().load_into_env(_secret_arn)

# ---------------------------------------------------------------------------
# Composition Root — wire all dependencies once at container startup
# ---------------------------------------------------------------------------
from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

from src.application.agent.graph import build_agent_graph  # noqa: E402
from src.application.use_cases.run_agent import RunAgentUseCase  # noqa: E402
from src.infrastructure.entrypoints.tool_registry import create_tools  # noqa: E402
from src.infrastructure.knowledge_base.faiss_vector_store import FAISSVectorStore  # noqa: E402
from src.infrastructure.llm.bedrock_adapter import BedrockChatAdapter  # noqa: E402
from src.infrastructure.observability.langfuse_adapter import LangfuseObservabilityHandler  # noqa: E402
from src.infrastructure.stock_data.yfinance_adapter import YFinanceStockDataProvider  # noqa: E402

_stock_provider = YFinanceStockDataProvider()
_vector_store = FAISSVectorStore.load("vectorstore")
_llm = BedrockChatAdapter()
_observability = LangfuseObservabilityHandler()
_tools = create_tools(_stock_provider, _vector_store)
_graph = build_agent_graph(_llm, _tools)
_run_use_case = RunAgentUseCase(_graph, _observability)

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict, context=None):
    """AgentCore entrypoint — streams agent response events.

    AgentCore validates the Cognito Bearer JWT before this function is called.
    We decode (but do not re-verify) the forwarded JWT to extract the user sub
    for Langfuse tracing.
    """
    query = payload.get("prompt", "")
    session_id = payload.get("session_id")
    user_id = _extract_sub(context)

    async for event in _run_use_case.execute(
        query=query,
        user_id=user_id,
        session_id=session_id,
    ):
        yield event


def _extract_sub(context) -> str | None:
    """Extract the 'sub' claim from the forwarded JWT payload without re-verifying."""
    try:
        auth_header = context.request_headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1]
        b64_payload = token.split(".")[1]
        # Add padding so standard base64 decode works
        b64_payload += "=" * (4 - len(b64_payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(b64_payload))
        return claims.get("sub")
    except Exception:
        return None


if __name__ == "__main__":
    app.run()
