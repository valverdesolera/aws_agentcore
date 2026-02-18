"""
LangGraph agent state definition.
See docs/CleanArchitecture.md — Phase 4 for the architectural rationale.
langgraph is the orchestration framework and is allowed in the application layer.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Shared state threaded through every node in the ReAct graph.

    messages: append-only list of LangChain BaseMessage objects managed by
              the add_messages reducer (handles deduplication and ordering).
    """

    messages: Annotated[list, add_messages]
