"""
Use-case: execute a user query through the compiled LangGraph ReAct agent.
See docs/CleanArchitecture.md — Phase 4 for the architectural rationale.
langchain_core.messages is treated as framework (not infrastructure) because
LangGraph is the orchestration framework used throughout the application layer.
"""

from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage

from src.domain.ports.observability_port import IObservabilityHandler


class RunAgentUseCase:
    def __init__(self, graph: Any, observability: IObservabilityHandler) -> None:
        """
        Args:
            graph:         Compiled LangGraph StateGraph returned by build_agent_graph().
            observability: IObservabilityHandler implementation (e.g. Langfuse adapter).
        """
        self._graph = graph
        self._observability = observability

    async def execute(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent events for a user *query*.

        Yields dicts of shape:
            {"node": str, "content": str, "type": str}

        Args:
            query:      The user's natural-language question.
            user_id:    Cognito sub for Langfuse tracing (optional).
            session_id: Client-supplied session id for Langfuse grouping (optional).
        """
        config = {
            "callbacks": [self._observability.as_callback()],
            "metadata": {
                "langfuse_user_id": user_id,
                "langfuse_session_id": session_id,
                "langfuse_tags": ["stock-agent"],
            },
            "recursion_limit": 10,
        }
        async for chunk in self._graph.astream(
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
