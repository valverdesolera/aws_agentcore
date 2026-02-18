"""
Infrastructure adapter: Langfuse → IObservabilityHandler.
See docs/CleanArchitecture.md — Phase 5 for the architectural rationale.

Langfuse is imported lazily inside the methods so the module can be loaded
even when LANGFUSE_* environment variables are not yet set (e.g. during testing).
The SecretsManagerAdapter.load_into_env() call in the AgentCore entrypoint must
run before this adapter is first used.
"""

from typing import Any

from src.domain.ports.observability_port import IObservabilityHandler


class LangfuseObservabilityHandler(IObservabilityHandler):
    """Wraps the Langfuse LangChain CallbackHandler."""

    def __init__(self) -> None:
        from langfuse.langchain import CallbackHandler
        self._handler = CallbackHandler()

    def as_callback(self) -> Any:
        """Return the Langfuse CallbackHandler for use in LangChain/LangGraph configs."""
        return self._handler

    def flush(self) -> None:
        """Flush pending traces to the Langfuse backend before the process exits."""
        from langfuse import get_client
        get_client().flush()
