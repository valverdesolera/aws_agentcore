# Phase 4 — LangGraph ReAct Agent

> **Architecture reference:** Before writing or reviewing any code for this phase, consult
> [`docs/CleanArchitecture.md`](../CleanArchitecture.md).
> Key files for this phase:
> - **Domain:** `src/domain/ports/llm_port.py`, `src/domain/ports/observability_port.py`
> - **Application:** `src/application/agent/state.py`, `src/application/agent/prompts.py`, `src/application/agent/graph.py`, `src/application/use_cases/run_agent.py`
> - **Infrastructure:** `src/infrastructure/llm/bedrock_adapter.py`, `src/infrastructure/entrypoints/tool_registry.py`

## Summary

Compose the two finance tools (Phase 2) and the document retrieval tool (Phase 3) into a single LangGraph ReAct-style agent. The agent uses a reasoning-action loop: the LLM reasons about which tool to call, executes the tool, observes the result, and continues until it can produce a final answer. All responses must be streamed via `.astream()`.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `langgraph` | Latest (`pip install langgraph`) |
| `langchain-aws` | For ChatBedrock LLM (or `langchain-openai` for OpenAI) |
| `langchain-core` | Core abstractions (tools, messages, state) |
| Phase 2 | `retrieve_realtime_stock_price`, `retrieve_historical_stock_price` |
| Phase 3 | `retrieve_financial_documents` (vector store retrieval tool) |

---

## Setup

### 1. Install Dependencies

```bash
pip install langgraph langchain-aws langchain-core
```

### 2. Project File Structure

```
src/
├── agent/
│   ├── __init__.py
│   ├── graph.py           # LangGraph ReAct agent definition
│   ├── state.py           # Agent state definition
│   └── test_agent.py      # Local test script
├── tools/
│   └── stock_tools.py     # From Phase 2
└── knowledge_base/
    └── retriever.py        # From Phase 3
```

---

## Requirements

### A. Agent State

Define the typed state that flows through the graph.

```python
# state.py
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State for the ReAct agent."""
    messages: Annotated[list, add_messages]
```

The `add_messages` reducer ensures messages are appended (not replaced) as they flow through graph nodes.

---

### B. ReAct Agent Graph

Build the graph with an LLM node that decides tool calls and a tool execution node.

```python
# graph.py
from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END

from src.agent.state import AgentState
from src.tools.stock_tools import retrieve_realtime_stock_price, retrieve_historical_stock_price
from src.knowledge_base.retriever import create_retrieval_tool


# --- LLM ---
llm = ChatBedrock(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    model_kwargs={"temperature": 0.0},
    region_name="us-east-1",
)
# NOTE: langchain-aws accepts both `model` and `model_id` as parameter names.
# Newer samples prefer `model=`. Both work.

# --- Tools ---
# The vectorstore must be loaded before this module is imported.
# In practice, load it at application startup (e.g., in agent_handler.py)
# and pass it into a factory function, or load it here at module level:
#   from src.knowledge_base.retriever import load_vectorstore
#   vectorstore = load_vectorstore("vectorstore")
retrieve_financial_documents = create_retrieval_tool(vectorstore)  # noqa: F821

tools = [
    retrieve_realtime_stock_price,
    retrieve_historical_stock_price,
    retrieve_financial_documents,
]
tools_by_name = {t.name: t for t in tools}
llm_with_tools = llm.bind_tools(tools)


# --- System Prompt ---
SYSTEM_PROMPT = """You are a financial research assistant specializing in Amazon (AMZN).

You have access to the following tools:
- retrieve_realtime_stock_price: Get current stock prices
- retrieve_historical_stock_price: Get historical stock prices over a date range
- retrieve_financial_documents: Search Amazon's financial reports (2024 Annual Report, Q2 and Q3 2025 Earnings Releases)

When answering:
1. Use the appropriate tool(s) to gather data before responding.
2. For stock price questions, use the stock price tools.
3. For questions about Amazon's business, financials, or reports, search the financial documents.
4. For comparison/analysis questions, use multiple tools as needed.
5. Always cite your sources when using financial document data.
6. Provide clear, well-structured answers.
"""


# --- Nodes ---
def llm_node(state: AgentState) -> dict:
    """Call the LLM to reason and potentially request tool calls."""
    # Only prepend the system prompt if it's not already in the message history.
    # This avoids sending it multiple times during multi-step tool chains.
    existing = state["messages"]
    if existing and isinstance(existing[0], SystemMessage):
        messages = existing
    else:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + existing
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    """Execute all tool calls from the last LLM message."""
    results = []
    last_message = state["messages"][-1]
    for tool_call in last_message.tool_calls:
        tool = tools_by_name[tool_call["name"]]
        result = tool.invoke(tool_call["args"])
        from langchain_core.messages import ToolMessage
        results.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )
    return {"messages": results}


# --- Routing ---
def should_continue(state: AgentState) -> str:
    """Route to tool_node if LLM made tool calls, otherwise END."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END


# --- Build Graph ---
def build_agent_graph():
    """Build and compile the ReAct agent graph.

    Returns a CompiledStateGraph (the result of StateGraph.compile()).
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("llm_node", llm_node)
    workflow.add_node("tool_node", tool_node)

    workflow.add_edge(START, "llm_node")
    workflow.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
    workflow.add_edge("tool_node", "llm_node")

    return workflow.compile()


graph = build_agent_graph()
```

**Reference:**
- LangGraph Quickstart: https://langchain-ai.github.io/langgraph/tutorials/introduction/
- LangGraph Streaming: https://langchain-ai.github.io/langgraph/how-tos/streaming/

---

### C. Streaming with `.astream()`

The assessment requires streaming via `.astream()`. This is an async generator that yields graph state updates as they happen.

```python
import asyncio
from langchain_core.messages import HumanMessage


async def stream_agent(query: str):
    """Stream the agent's response for a given query."""
    input_state = {"messages": [HumanMessage(content=query)]}

    # Stream mode "values" yields the full state at each step
    async for chunk in graph.astream(input_state, stream_mode="values"):
        last_msg = chunk["messages"][-1]
        # Print the latest message content
        if hasattr(last_msg, "content") and last_msg.content:
            print(last_msg.content)

    # OR: stream_mode="updates" yields only changed state per node
    async for chunk in graph.astream(input_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            print(f"[{node_name}]", update["messages"][-1])
```

**Stream modes:**
- `"values"` — yields the full graph state after each node completes
- `"updates"` — yields only the delta (changed state) per node
- `"messages"` — yields individual messages as they stream from the LLM

For the FastAPI SSE endpoint (Phase 6), `stream_mode="updates"` or `"messages"` is most appropriate to send incremental data to the client.

**Reference:** https://langchain-ai.github.io/langgraph/how-tos/streaming/#filter-by-llm-invocation

---

### D. ReAct Loop Behavior

The graph implements a standard ReAct loop:

```
START → llm_node → [has tool calls?]
                     ├── YES → tool_node → llm_node (loop back)
                     └── NO  → END (final answer)
```

1. **Reason:** The LLM receives the conversation history + system prompt and decides whether to call a tool or produce a final answer.
2. **Act:** If tool calls are present, the `tool_node` executes them and appends `ToolMessage` results.
3. **Observe:** The LLM receives the tool results and either calls more tools or generates the final response.

---

## Implementation Notes

1. **LLM choice.** Claude 3 Sonnet via Bedrock is recommended for tool-calling reliability. Ensure the model is enabled in your Bedrock console for `us-east-1` (account `531241048046`, profile `juanvalsol`). Set `AWS_PROFILE=juanvalsol` before running the agent locally.

   > **Performance note:** The `llm_node` checks whether the system prompt is already present before prepending it. This prevents it from being sent multiple times during multi-step tool chains. An alternative approach is to inject the system message once at graph entry (as part of the initial input state).

2. **Tool calling format.** `ChatBedrock.bind_tools(tools)` automatically formats the tools into the correct schema for the Anthropic API. The LLM returns structured `tool_calls` in its response message.

3. **Multiple tool calls.** The LLM may call multiple tools in a single turn (e.g., both `retrieve_realtime_stock_price` and `retrieve_financial_documents` for a combined query). The `tool_node` handles all tool calls from the last message.

4. **Max iterations.** Add a recursion limit to prevent infinite loops:
   ```python
   config = {"recursion_limit": 10}
   async for chunk in graph.astream(input_state, config=config, stream_mode="updates"):
       ...
   ```

5. **System prompt tuning.** The system prompt is critical for correct tool selection. Test it against all five UAT queries and adjust if the agent selects the wrong tools.

---

## UAT Query Coverage

| Query | Expected Tool(s) |
|---|---|
| "What is the stock price for Amazon right now?" | `retrieve_realtime_stock_price` |
| "What were the stock prices for Amazon in Q4 last year?" | `retrieve_historical_stock_price` |
| "Compare Amazon's recent stock performance to what analysts predicted in their reports" | `retrieve_historical_stock_price` + `retrieve_financial_documents` |
| "I'm researching AMZN give me the current price and any relevant information about their AI business" | `retrieve_realtime_stock_price` + `retrieve_financial_documents` |
| "What is the total amount of office space Amazon owned in North America in 2024?" | `retrieve_financial_documents` |

---

## Verification Checklist

- [ ] Graph compiles without errors
- [ ] `graph.astream(...)` yields updates for each node
- [ ] Agent correctly routes to `retrieve_realtime_stock_price` for real-time queries
- [ ] Agent correctly routes to `retrieve_historical_stock_price` for historical queries
- [ ] Agent correctly routes to `retrieve_financial_documents` for document queries
- [ ] Agent uses multiple tools for combined queries
- [ ] All 5 UAT queries produce reasonable answers
- [ ] Recursion limit prevents infinite tool-calling loops
