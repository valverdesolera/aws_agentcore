# Phase 5 — Observability with Langfuse

## Summary

Integrate Langfuse into the LangGraph agent so every invocation is traced end-to-end. Langfuse captures LLM calls, tool executions, and retrieval operations as hierarchical spans, providing full visibility into agent behavior. The free cloud tier is used as specified in the requirements.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `langfuse` | Latest (`pip install langfuse`) |
| Langfuse Cloud Account | Already configured — org: `PersonalProjects`, project: `teilur-stock-agent` |
| Phase 4 | LangGraph agent must exist to attach tracing |

---

## Setup

### 1. Langfuse Cloud Account (Already Configured)

The Langfuse account and project are already set up:

- **Organization:** `PersonalProjects`
- **Project:** `teilur-stock-agent`
- **Region host:** `https://us.cloud.langfuse.com` (US region)

### 2. Install Dependencies

```bash
pip install langfuse
```

### 3. Environment Variables

Add these to your `.env` file (gitignored — **never commit the secret key to the repo**):

```bash
# .env
LANGFUSE_SECRET_KEY="sk-lf-REPLACE-WITH-YOUR-SECRET-KEY"
LANGFUSE_PUBLIC_KEY="pk-lf-REPLACE-WITH-YOUR-PUBLIC-KEY"
LANGFUSE_BASE_URL="https://us.cloud.langfuse.com"
```

> **Note:** The environment variable name is `LANGFUSE_BASE_URL` (not `LANGFUSE_HOST`) because this project uses the US-region Langfuse endpoint. The Langfuse Python SDK automatically reads these from the environment when initialized.

For AgentCore cloud deployment, the application fetches these values from **AWS Secrets Manager** at startup (see Phase 1 for the `secrets.tf` Terraform resource). Only the non-sensitive Secrets Manager ARN is passed as an environment variable:

```bash
agentcore deploy \
  --env LANGFUSE_SECRET_ARN=<ARN_FROM_TERRAFORM_OUTPUT>
```

> **Note:** The `--env` flag belongs to `agentcore deploy` (the deployment command), not `agentcore configure`.

The application code resolves the secret at startup (see Phase 6 for the bootstrap snippet). **Never pass plaintext Langfuse keys via `--env` flags.**

> **Security reminder:** Do not hardcode these values in source code or commit them to git. Use `.env` locally and Secrets Manager for cloud deployments.

---

## Requirements

### A. Langfuse CallbackHandler

Langfuse provides a native `CallbackHandler` for LangChain/LangGraph. Pass it via the `config` parameter to `graph.stream()` or `graph.astream()`.

```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

# Initialize Langfuse client
langfuse = get_client()

# Create the callback handler
langfuse_handler = CallbackHandler()
```

**Reference:** https://langfuse.com/docs/integrations/langchain/tracing

---

### B. Attach to LangGraph Agent

Pass the handler in the `config["callbacks"]` when invoking the agent graph.

```python
from langchain_core.messages import HumanMessage


async def stream_agent_with_tracing(query: str, user_id: str = None, session_id: str = None):
    """Stream the agent with Langfuse tracing enabled."""
    input_state = {"messages": [HumanMessage(content=query)]}

    # Build config with Langfuse callback
    config = {
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_user_id": user_id,
            "langfuse_session_id": session_id,
            "langfuse_tags": ["stock-agent", "production"],
        },
        "recursion_limit": 10,
    }

    async for chunk in graph.astream(input_state, config=config, stream_mode="updates"):
        for node_name, update in chunk.items():
            yield node_name, update
```

**What gets traced automatically:**
- Each LLM call (input messages, output, model parameters, token usage)
- Each tool call (tool name, input arguments, output)
- Graph node transitions
- Total latency per trace

---

### C. Custom Trace Metadata (Langfuse v3)

Enrich traces with user/session context for filtering in the Langfuse dashboard. In Langfuse v3, pass these via the `config["metadata"]` dict with the `langfuse_` prefix:

```python
config = {
    "callbacks": [langfuse_handler],
    "metadata": {
        "langfuse_user_id": "user_123",         # Links trace to a user
        "langfuse_session_id": "session_456",    # Groups traces in a session
        "langfuse_tags": ["stock-agent", "v1"],  # Filterable tags
    },
}

# Pass to graph invocation
async for chunk in graph.astream(input_state, config=config, stream_mode="updates"):
    ...
```

> **Important:** Do NOT pass `user_id`, `session_id`, or `tags` as constructor arguments to `CallbackHandler()` when using the `langfuse.langchain` import (v3). Use the `config["metadata"]` approach shown above. See [Langfuse LangChain integration docs](https://langfuse.com/docs/integrations/langchain/tracing) for the full reference.

This enables:
- Per-user trace filtering in the Langfuse dashboard
- Session grouping across multiple queries
- Tag-based filtering for debugging

---

### D. Flushing Traces

Langfuse batches traces and sends them asynchronously. In a long-running server (FastAPI), this works automatically. For scripts or notebooks, explicitly flush:

```python
from langfuse import get_client

# At the end of a script or notebook cell
langfuse = get_client()
langfuse.flush()
```

---

## Integration with FastAPI (Phase 6 Preview)

In the FastAPI endpoint, create a fresh handler per request and pass user context via `config["metadata"]` (the v3 recommended approach):

```python
from langfuse.langchain import CallbackHandler


@app.post("/query")
async def query_endpoint(request: QueryRequest):
    # Create per-request handler
    handler = CallbackHandler()

    # Pass user/session context via metadata (Langfuse v3 pattern)
    config = {
        "callbacks": [handler],
        "metadata": {
            "langfuse_user_id": request.user_id,
            "langfuse_session_id": request.session_id,
            "langfuse_tags": ["api-request"],
        },
    }

    async def event_stream():
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content=request.query)]},
            config=config,
            stream_mode="updates",
        ):
            yield format_sse(chunk)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

> **Langfuse v3 note:** Pass `user_id`, `session_id`, and `tags` via `config["metadata"]` keys `langfuse_user_id`, `langfuse_session_id`, and `langfuse_tags` respectively. The older v2 pattern of passing these as `CallbackHandler(user_id=..., session_id=...)` constructor arguments used a different import path (`from langfuse.callback import CallbackHandler`) and may not work correctly with the v3 `langfuse.langchain.CallbackHandler`.

---

## Implementation Notes

1. **Free tier limits.** Langfuse cloud free tier allows 50K observations/month. This is sufficient for development and the UAT demo. Monitor usage in the Langfuse dashboard.

2. **No code changes to the agent graph.** Langfuse is injected purely via the callback mechanism — the agent code itself does not import or reference Langfuse.

3. **Trace hierarchy.** A single graph invocation produces one top-level "trace" containing:
   - **Generations** — one per LLM call (with token counts, latency)
   - **Spans** — one per tool execution
   - **Events** — state transitions between nodes

4. **Screenshot capture for UAT.** After running each UAT query, open the Langfuse dashboard and capture:
   - The trace timeline view (shows LLM calls and tool calls)
   - The trace detail view (shows input/output for each span)
   - These screenshots go into the Phase 7 Jupyter notebook

5. **Langfuse API for programmatic access.** Instead of screenshots, you can fetch traces via the API:
   ```python
   from langfuse import get_client

   langfuse = get_client()
   traces = langfuse.fetch_traces(limit=5)
   for trace in traces.data:
       print(trace.id, trace.name, trace.latency)
   ```

---

## Verification Checklist

- [x] Langfuse cloud account created and API keys generated (org: `PersonalProjects`, project: `teilur-stock-agent`)
- [ ] `LANGFUSE_SECRET_ARN` env var is passed to `agentcore deploy` (not plaintext keys)
- [ ] `langfuse_handler` initializes without errors
- [ ] Running the agent with the callback produces traces visible in the Langfuse dashboard
- [ ] Traces show LLM calls with model name, input/output, and token usage
- [ ] Traces show tool calls with tool name and arguments
- [ ] User ID and session ID metadata appear in the trace detail
- [ ] Tags are filterable in the Langfuse dashboard
- [ ] Traces are flushed correctly (no missing data after script exits)
