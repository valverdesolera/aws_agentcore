"""
LangGraph ReAct agent graph factory.
See docs/CleanArchitecture.md — Phase 4 for the architectural rationale.

Dependency-injection contract:
  - Receives ILanguageModel and a list of @tool-decorated callables.
  - Never imports ChatBedrock, langfuse, yfinance, faiss, or boto3 directly.
  - langchain_core and langgraph are treated as orchestration-framework imports,
    acceptable in the application layer.
"""

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from src.application.agent.prompts import SYSTEM_PROMPT
from src.application.agent.state import AgentState
from src.domain.ports.llm_port import ILanguageModel


def build_agent_graph(llm: ILanguageModel, tools: list):
    """Build and compile the ReAct agent graph.

    Args:
        llm:   ILanguageModel implementation — injected, no direct SDK reference.
        tools: List of LangChain @tool-decorated callables from tool_registry.

    Returns:
        Compiled LangGraph CompiledStateGraph ready for astream() calls.
    """
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    def llm_node(state: AgentState) -> dict:
        """Reasoning step: prepend system prompt if absent, then call the LLM."""
        existing = state["messages"]
        if existing and isinstance(existing[0], SystemMessage):
            messages = existing
        else:
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + existing
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def tool_node(state: AgentState) -> dict:
        """Action step: invoke every tool call requested by the last LLM message."""
        results: list[ToolMessage] = []
        last_message = state["messages"][-1]
        for tool_call in last_message.tool_calls:
            tool = tools_by_name[tool_call["name"]]
            output = tool.invoke(tool_call["args"])
            results.append(
                ToolMessage(content=str(output), tool_call_id=tool_call["id"])
            )
        return {"messages": results}

    def should_continue(state: AgentState) -> str:
        """Route: if the LLM made tool calls, execute them; otherwise end."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tool_node"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("llm_node", llm_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_edge(START, "llm_node")
    workflow.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
    workflow.add_edge("tool_node", "llm_node")
    return workflow.compile()
