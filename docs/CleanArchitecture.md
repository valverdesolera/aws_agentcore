# Clean Architecture Audit — Teilur Stock Agent

> **Coding standard reference** — Every file under `src/` must follow the rules in this document.
> Before writing or reviewing code for any phase, open this document and verify:
> 1. Which layer the file belongs to (Domain / Application / Infrastructure).
> 2. Which imports are allowed from that layer.
> 3. Whether the Dependency Rule is satisfied (Infrastructure → Application → Domain only).

## Overview

This document audits every task in each phase plan (`docs/phases/`) against Clean Architecture principles. For each task it identifies the correct architectural layer, defines the required interfaces/contracts to decouple the application core from external tools (DB, APIs, UI), and proposes a refactored file-structure under `src/domain`, `src/application`, and `src/infrastructure`.

### Layer Definitions

| Layer | Responsibility | Allowed dependencies |
|---|---|---|
| **Domain** | Core business rules, entities, value objects. Zero external dependencies. | Nothing outside this layer |
| **Application** | Use-cases, orchestration, port interfaces. Depends only on Domain. | Domain only |
| **Infrastructure** | Adapters that satisfy the ports: HTTP clients, vector stores, LLM SDKs, AWS services, FastAPI, AgentCore. | Application + Domain |

The **Dependency Rule**: source code dependencies must point **inward only** — Infrastructure → Application → Domain.

---

## Proposed Global File Structure

```
src/
├── domain/
│   ├── entities/
│   │   ├── stock_price.py          # StockPrice, HistoricalRecord value objects
│   │   └── document_chunk.py       # DocumentChunk entity
│   ├── ports/
│   │   ├── stock_data_port.py      # IStockDataProvider (abstract)
│   │   ├── document_retrieval_port.py  # IDocumentRetriever (abstract)
│   │   ├── llm_port.py             # ILanguageModel (abstract)
│   │   ├── vector_store_port.py    # IVectorStore (abstract)
│   │   ├── secret_store_port.py    # ISecretStore (abstract)
│   │   └── observability_port.py   # IObservabilityHandler (abstract)
│   └── __init__.py
│
├── application/
│   ├── use_cases/
│   │   ├── get_realtime_price.py       # GetRealtimeStockPriceUseCase
│   │   ├── get_historical_prices.py    # GetHistoricalStockPricesUseCase
│   │   ├── retrieve_documents.py       # RetrieveFinancialDocumentsUseCase
│   │   └── run_agent.py                # RunAgentUseCase (orchestrates the ReAct loop)
│   ├── agent/
│   │   ├── graph.py            # LangGraph graph definition (depends on ports, not adapters)
│   │   ├── state.py            # AgentState TypedDict
│   │   └── prompts.py          # System prompt constants
│   ├── services/
│   │   └── knowledge_ingestor.py   # IngestDocumentsService (PDF → chunks → index)
│   └── __init__.py
│
├── infrastructure/
│   ├── stock_data/
│   │   └── yfinance_adapter.py     # YFinanceStockDataProvider implements IStockDataProvider
│   ├── knowledge_base/
│   │   ├── pdf_loader.py           # Downloads + parses PDFs using PyPDF
│   │   ├── faiss_vector_store.py   # FAISSVectorStore implements IVectorStore
│   │   └── ingest.py               # CLI entry point: calls IngestDocumentsService
│   ├── llm/
│   │   └── bedrock_adapter.py      # BedrockChatAdapter implements ILanguageModel
│   ├── observability/
│   │   └── langfuse_adapter.py     # LangfuseObservabilityHandler implements IObservabilityHandler
│   ├── auth/
│   │   └── cognito_validator.py    # Cognito JWKS validation (infrastructure concern)
│   ├── secrets/
│   │   └── secrets_manager_adapter.py  # SecretsManagerAdapter implements ISecretStore
│   └── entrypoints/
│       ├── fastapi_app.py          # FastAPI HTTP entry point (local dev)
│       └── agentcore_handler.py    # AgentCore BedrockAgentCoreApp entry point
│
infrastructure/         # Terraform (outside src — purely provisioning, not Python)
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── cognito.tf
│   ├── iam.tf
│   ├── ecr.tf
│   └── secrets.tf
│
notebooks/
│   └── demo.ipynb
│
vectorstore/            # Pre-built FAISS index (committed or uploaded to S3)
data/
│   └── pdfs/           # Downloaded PDFs (gitignored)
```

---

## Phase 1 — Infrastructure & Auth Foundation

### Audit Summary

Phase 1 is purely about cloud provisioning (Terraform) and CI bootstrap. There is no Python application logic here, so the Clean Architecture layers are not violated. However, the phase plan implicitly places the Cognito JWT-validation logic (used in Phase 6) inside `src/auth/cognito.py` without defining an abstraction. That coupling must be addressed.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. Cognito User Pool (Terraform) | `infrastructure/` | **Infrastructure (provisioning)** | Correct — stays in `infrastructure/` |
| B. IAM Roles (Terraform) | `infrastructure/` | **Infrastructure (provisioning)** | Correct |
| C. Secrets Manager (Terraform + secret values) | `infrastructure/` | **Infrastructure (provisioning)** | Correct |
| D. ECR Repository (Terraform) | `infrastructure/` | **Infrastructure (provisioning)** | Correct |
| E. Terraform outputs | `infrastructure/outputs.tf` | **Infrastructure (provisioning)** | Correct |
| JWT validation (used in Phase 6, bootstrapped here) | `src/auth/cognito.py` | **Infrastructure** | Must implement a port defined in Domain |

### Required Interfaces / Contracts

```python
# src/domain/ports/secret_store_port.py
from abc import ABC, abstractmethod

class ISecretStore(ABC):
    """Port: retrieve named secrets at runtime."""

    @abstractmethod
    def get_secret(self, secret_arn: str) -> dict:
        """Return the secret as a key-value dict."""
        ...
```

```python
# src/domain/ports/token_validator_port.py
from abc import ABC, abstractmethod

class ITokenValidator(ABC):
    """Port: validate and decode an authentication token."""

    @abstractmethod
    def validate(self, token: str) -> dict:
        """Validate the token and return the decoded claims.

        Raises:
            AuthenticationError: if the token is invalid or expired.
        """
        ...
```

The concrete adapters (`SecretsManagerAdapter`, `CognitoTokenValidator`) live in `src/infrastructure/` and implement these ports. The application core never imports `boto3`, `jose`, or `httpx` directly.

### Refactored File Structure (Phase 1 additions)

```
infrastructure/              # Terraform — unchanged
│   ├── main.tf
│   ├── cognito.tf
│   ├── iam.tf
│   ├── ecr.tf
│   └── secrets.tf

src/
├── domain/
│   └── ports/
│       ├── secret_store_port.py       # NEW — ISecretStore
│       └── token_validator_port.py    # NEW — ITokenValidator
└── infrastructure/
    ├── secrets/
    │   └── secrets_manager_adapter.py # NEW — implements ISecretStore via boto3
    └── auth/
        └── cognito_validator.py       # NEW — implements ITokenValidator via python-jose
```

---

## Phase 2 — Finance Tools

### Audit Summary

The plan places both tools in `src/tools/stock_tools.py` as LangChain `@tool`-decorated functions. This conflates two concerns: the **business rule** (what stock data means, what fields are returned) with the **infrastructure adapter** (how yfinance is called). Decorating with `@tool` also ties the domain entity directly to LangChain's framework.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. `retrieve_realtime_stock_price` — business logic | `src/tools/stock_tools.py` | **Domain / Application** | The shape of `StockPrice` is a domain entity; the use-case is Application |
| A. yfinance API call | `src/tools/stock_tools.py` | **Infrastructure** | `yf.Ticker`, `fast_info`, etc. belong in an adapter |
| B. `retrieve_historical_stock_price` — business logic | `src/tools/stock_tools.py` | **Domain / Application** | Same split applies |
| B. yfinance DataFrame parsing | `src/tools/stock_tools.py` | **Infrastructure** | DataFrame → dict translation is an adapter responsibility |
| `@tool` decorator binding | `src/tools/stock_tools.py` | **Infrastructure** | LangChain tool wrappers are framework adapters, not domain logic |

### Required Interfaces / Contracts

```python
# src/domain/entities/stock_price.py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class StockPrice:
    symbol: str
    current_price: Optional[float]
    previous_close: Optional[float]
    open: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[int]
    currency: str
    market_state: str

@dataclass(frozen=True)
class HistoricalRecord:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass(frozen=True)
class HistoricalPrices:
    symbol: str
    period: str
    interval: str
    records: list[HistoricalRecord]
```

```python
# src/domain/ports/stock_data_port.py
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.stock_price import StockPrice, HistoricalPrices

class IStockDataProvider(ABC):
    """Port: retrieve stock market data."""

    @abstractmethod
    def get_realtime_price(self, symbol: str) -> StockPrice:
        ...

    @abstractmethod
    def get_historical_prices(
        self,
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> HistoricalPrices:
        ...
```

```python
# src/application/use_cases/get_realtime_price.py
from src.domain.ports.stock_data_port import IStockDataProvider
from src.domain.entities.stock_price import StockPrice

class GetRealtimeStockPriceUseCase:
    def __init__(self, provider: IStockDataProvider):
        self._provider = provider

    def execute(self, symbol: str) -> StockPrice:
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        return self._provider.get_realtime_price(symbol.upper())
```

```python
# src/infrastructure/stock_data/yfinance_adapter.py
import yfinance as yf
from src.domain.ports.stock_data_port import IStockDataProvider
from src.domain.entities.stock_price import StockPrice, HistoricalPrices, HistoricalRecord

class YFinanceStockDataProvider(IStockDataProvider):
    """Infrastructure adapter: fetches data from yfinance."""

    def get_realtime_price(self, symbol: str) -> StockPrice:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        fast_info = ticker.fast_info
        return StockPrice(
            symbol=symbol,
            current_price=getattr(fast_info, "last_price", None) or info.get("currentPrice"),
            previous_close=getattr(fast_info, "previous_close", None) or info.get("previousClose"),
            open=info.get("open"),
            day_high=info.get("dayHigh"),
            day_low=info.get("dayLow"),
            volume=info.get("volume"),
            currency=info.get("currency", "USD"),
            market_state=info.get("marketState", "UNKNOWN"),
        )

    def get_historical_prices(self, symbol, period="3mo", interval="1d",
                              start_date=None, end_date=None) -> HistoricalPrices:
        ticker = yf.Ticker(symbol)
        history = (
            ticker.history(start=start_date, end=end_date, interval=interval)
            if start_date
            else ticker.history(period=period, interval=interval)
        )
        records = [
            HistoricalRecord(
                date=date.strftime("%Y-%m-%d"),
                open=round(row["Open"], 2),
                high=round(row["High"], 2),
                low=round(row["Low"], 2),
                close=round(row["Close"], 2),
                volume=int(row["Volume"]),
            )
            for date, row in history.iterrows()
        ]
        period_label = period if not start_date else f"{start_date} to {end_date or 'today'}"
        return HistoricalPrices(symbol=symbol, period=period_label, interval=interval, records=records)
```

The `@tool` decorator wrapping lives in the infrastructure layer (or in a dedicated `tool_registry.py` inside `infrastructure/`), not inside domain or application code.

### Refactored File Structure (Phase 2)

```
src/
├── domain/
│   ├── entities/
│   │   └── stock_price.py             # StockPrice, HistoricalRecord, HistoricalPrices
│   └── ports/
│       └── stock_data_port.py         # IStockDataProvider
├── application/
│   └── use_cases/
│       ├── get_realtime_price.py      # GetRealtimeStockPriceUseCase
│       └── get_historical_prices.py   # GetHistoricalStockPricesUseCase
└── infrastructure/
    └── stock_data/
        └── yfinance_adapter.py        # YFinanceStockDataProvider (yfinance calls here)
```

> **Removed:** `src/tools/stock_tools.py` — LangChain `@tool` wrappers move to `src/infrastructure/entrypoints/tool_registry.py` and reference the use-cases.

---

## Phase 3 — Knowledge Base & Document Retrieval

### Audit Summary

The plan places ingestion logic, embedding calls, FAISS operations, and retrieval all within `src/knowledge_base/`. This bundles Infrastructure adapters (PyPDF, FAISS, OpenAI/Bedrock embedding APIs) with Application orchestration (chunking strategy, ingest flow) and Domain concepts (what a `DocumentChunk` is). These must be separated.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. PDF download (`requests.get`) | `src/knowledge_base/ingest.py` | **Infrastructure** | HTTP I/O is an infrastructure concern |
| A. PDF parsing (`PyPDFLoader`) | `src/knowledge_base/ingest.py` | **Infrastructure** | Framework adapter |
| A. `DocumentChunk` / `Document` shape | `src/knowledge_base/ingest.py` (implicit) | **Domain** | Entity definition belongs in domain |
| B. Chunking strategy (sizes, separators) | `src/knowledge_base/ingest.py` | **Application** | Business rule: "what constitutes a good chunk for our retrieval" |
| C. Embedding model call | `src/knowledge_base/ingest.py` | **Infrastructure** | Calls to OpenAI / Bedrock are external |
| C. FAISS index creation & persistence | `src/knowledge_base/ingest.py` | **Infrastructure** | Vector store is an external tool |
| C. `load_vectorstore` | `src/knowledge_base/retriever.py` | **Infrastructure** | Deserialization from disk is I/O |
| D. `retrieve_financial_documents` use-case | `src/knowledge_base/retriever.py` | **Application** | Orchestration of retrieval belongs in Application |
| D. `retriever.invoke(query)` call | `src/knowledge_base/retriever.py` | **Infrastructure** | The actual vector-store call is Infrastructure |
| D. `@tool` decoration | `src/knowledge_base/retriever.py` | **Infrastructure** | LangChain binding is a framework adapter |

### Required Interfaces / Contracts

```python
# src/domain/entities/document_chunk.py
from dataclasses import dataclass

@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source_file: str
    page: int
    chunk_id: int
```

```python
# src/domain/ports/vector_store_port.py
from abc import ABC, abstractmethod
from src.domain.entities.document_chunk import DocumentChunk

class IVectorStore(ABC):
    """Port: semantic search over a collection of document chunks."""

    @abstractmethod
    def similarity_search(self, query: str, k: int = 5) -> list[DocumentChunk]:
        ...

    @abstractmethod
    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        ...

    @abstractmethod
    def persist(self, path: str) -> None:
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "IVectorStore":
        ...
```

```python
# src/domain/ports/document_loader_port.py
from abc import ABC, abstractmethod
from src.domain.entities.document_chunk import DocumentChunk

class IDocumentLoader(ABC):
    """Port: load raw documents from an external source."""

    @abstractmethod
    def load(self, source: str) -> list[DocumentChunk]:
        """Load a document from a URL or file path and return raw chunks."""
        ...
```

```python
# src/application/services/knowledge_ingestor.py
from src.domain.ports.document_loader_port import IDocumentLoader
from src.domain.ports.vector_store_port import IVectorStore
from src.domain.entities.document_chunk import DocumentChunk

class IngestDocumentsService:
    """Application service: orchestrates the full ingestion pipeline."""

    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200

    def __init__(self, loader: IDocumentLoader, vector_store: IVectorStore):
        self._loader = loader
        self._vector_store = vector_store

    def ingest(self, sources: list[str], persist_path: str) -> int:
        all_chunks: list[DocumentChunk] = []
        for source in sources:
            all_chunks.extend(self._loader.load(source))
        # Chunking strategy (application rule — not yfinance/FAISS specific)
        chunks = self._apply_chunking(all_chunks)
        self._vector_store.add_documents(chunks)
        self._vector_store.persist(persist_path)
        return len(chunks)

    def _apply_chunking(self, docs: list[DocumentChunk]) -> list[DocumentChunk]:
        # Splitting logic lives here; uses no external library references
        ...
```

```python
# src/application/use_cases/retrieve_documents.py
from src.domain.ports.vector_store_port import IVectorStore

class RetrieveFinancialDocumentsUseCase:
    def __init__(self, vector_store: IVectorStore):
        self._vector_store = vector_store

    def execute(self, query: str, k: int = 5) -> str:
        chunks = self._vector_store.similarity_search(query, k=k)
        results = [
            f"[Source: {c.source_file}, Page: {c.page}]\n{c.content}"
            for c in chunks
        ]
        return "\n\n---\n\n".join(results)
```

### Refactored File Structure (Phase 3)

```
src/
├── domain/
│   ├── entities/
│   │   └── document_chunk.py              # DocumentChunk entity
│   └── ports/
│       ├── vector_store_port.py           # IVectorStore
│       └── document_loader_port.py        # IDocumentLoader
├── application/
│   ├── use_cases/
│   │   └── retrieve_documents.py          # RetrieveFinancialDocumentsUseCase
│   └── services/
│       └── knowledge_ingestor.py          # IngestDocumentsService (chunking + orchestration)
└── infrastructure/
    └── knowledge_base/
        ├── pdf_loader.py                  # PyPDFLoader + requests adapter → IDocumentLoader
        ├── faiss_vector_store.py          # FAISS + embedding model adapter → IVectorStore
        └── ingest.py                      # CLI entry point calling IngestDocumentsService
```

> **Removed:** `src/knowledge_base/` flat directory — split into domain, application, and infrastructure as above.

---

## Phase 4 — LangGraph ReAct Agent

### Audit Summary

The plan puts everything in `src/agent/graph.py`: LLM instantiation (`ChatBedrock`), tool binding, graph wiring, system prompt, and node logic. This directly couples the orchestration logic to LangGraph's internals and the Bedrock SDK. The agent loop logic (Reason-Act-Observe) is an **Application** concern; the LLM call and tool execution wrappers are **Infrastructure**.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. `AgentState` TypedDict | `src/agent/state.py` | **Application** | Graph state schema is application-level |
| B. LLM instantiation (`ChatBedrock(...)`) | `src/agent/graph.py` | **Infrastructure** | Creating a Bedrock client is infrastructure |
| B. `llm.bind_tools(tools)` | `src/agent/graph.py` | **Infrastructure** | LangChain tool binding is a framework adapter |
| B. `llm_node` — reasoning step | `src/agent/graph.py` | **Application** | The Reason step (call LLM with state) is orchestration |
| B. `tool_node` — tool execution | `src/agent/graph.py` | **Application** | The Act step (dispatch tool calls) is orchestration |
| B. `should_continue` routing | `src/agent/graph.py` | **Application** | Conditional routing logic is a business rule of the ReAct loop |
| B. `build_agent_graph()` | `src/agent/graph.py` | **Application** | Graph assembly is Application (depends on ports, not SDK directly) |
| B. System prompt constant | `src/agent/graph.py` (inline) | **Application** | Prompts are application-level configuration |
| C. `.astream()` invocation | `src/agent/test_agent.py` | **Infrastructure / Entrypoint** | Streaming invocation belongs in the entry point adapter |

### Required Interfaces / Contracts

```python
# src/domain/ports/llm_port.py
from abc import ABC, abstractmethod
from typing import Any

class ILanguageModel(ABC):
    """Port: invoke a language model with a list of messages."""

    @abstractmethod
    def invoke(self, messages: list[Any]) -> Any:
        """Return an AI message (potentially with tool_calls)."""
        ...

    @abstractmethod
    def bind_tools(self, tools: list) -> "ILanguageModel":
        """Return a new model instance with tools bound."""
        ...
```

```python
# src/domain/ports/observability_port.py
from abc import ABC, abstractmethod
from typing import Any

class IObservabilityHandler(ABC):
    """Port: callback handler for tracing agent invocations."""

    @abstractmethod
    def as_callback(self) -> Any:
        """Return the framework-specific callback object."""
        ...

    @abstractmethod
    def flush(self) -> None:
        ...
```

The graph in `src/application/agent/graph.py` receives an `ILanguageModel` and `IObservabilityHandler` via dependency injection — it does not import `ChatBedrock` or `langfuse` directly.

```python
# src/application/agent/graph.py  (simplified sketch)
from src.application.agent.state import AgentState
from src.domain.ports.llm_port import ILanguageModel

def build_agent_graph(llm: ILanguageModel, tools: list):
    """Build the ReAct graph given injected dependencies."""
    llm_with_tools = llm.bind_tools(tools)
    # ... graph wiring using llm_with_tools, no direct SDK references
```

### Refactored File Structure (Phase 4)

```
src/
├── domain/
│   └── ports/
│       └── llm_port.py                    # ILanguageModel
├── application/
│   └── agent/
│       ├── state.py                       # AgentState (unchanged)
│       ├── prompts.py                     # SYSTEM_PROMPT constant (moved out of graph.py)
│       └── graph.py                       # ReAct graph; receives ILanguageModel via DI
└── infrastructure/
    └── llm/
        └── bedrock_adapter.py             # BedrockChatAdapter implements ILanguageModel
```

> **Removed:** Direct `from langchain_aws import ChatBedrock` inside `graph.py`. Bedrock instantiation moves to `infrastructure/llm/bedrock_adapter.py` and is injected at startup.

---

## Phase 5 — Observability with Langfuse

### Audit Summary

The plan has Langfuse's `CallbackHandler` instantiated directly inside both `app.py` and `agent_handler.py` — and the secrets bootstrap (`_load_langfuse_secrets()`) lives inside the AgentCore entry point. Observability concerns must be hidden behind a port so the agent graph is not coupled to Langfuse.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. `CallbackHandler()` instantiation | `app.py` / `agent_handler.py` | **Infrastructure** | Langfuse SDK is an external tool |
| A. `from langfuse.langchain import CallbackHandler` | `graph.py` (preview) | **Infrastructure** | LangChain-Langfuse binding is a framework adapter |
| B. Passing `config["callbacks"]` to `graph.astream()` | `app.py` / `agent_handler.py` | **Application / Entrypoint** | Wiring callback into the invocation is orchestration at the entry point |
| C. Custom trace metadata (user_id, session_id, tags) | `app.py` / `agent_handler.py` | **Application** | Deciding what context to attach to a trace is an application rule |
| D. `langfuse.flush()` | `agent_handler.py` | **Infrastructure** | SDK lifecycle management is infrastructure |
| Secrets bootstrap `_load_langfuse_secrets()` | `agent_handler.py` | **Infrastructure** | Secret resolution belongs in the Infrastructure bootstrap, not the entrypoint |

### Required Interfaces / Contracts

```python
# src/domain/ports/observability_port.py
from abc import ABC, abstractmethod
from typing import Any

class IObservabilityHandler(ABC):
    """Port: tracing and observability callback."""

    @abstractmethod
    def as_callback(self) -> Any:
        """Return the framework-native callback object (e.g. LangChain CallbackHandler)."""
        ...

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered telemetry data."""
        ...
```

```python
# src/infrastructure/observability/langfuse_adapter.py
from langfuse.langchain import CallbackHandler
from src.domain.ports.observability_port import IObservabilityHandler

class LangfuseObservabilityHandler(IObservabilityHandler):
    def __init__(self):
        self._handler = CallbackHandler()

    def as_callback(self):
        return self._handler

    def flush(self):
        from langfuse import get_client
        get_client().flush()
```

The secret bootstrap is extracted to a dedicated infrastructure module:

```python
# src/infrastructure/secrets/secrets_manager_adapter.py
import json
import boto3
from src.domain.ports.secret_store_port import ISecretStore

class SecretsManagerAdapter(ISecretStore):
    def __init__(self, region: str = "us-east-1"):
        self._client = boto3.client("secretsmanager", region_name=region)

    def get_secret(self, secret_arn: str) -> dict:
        response = self._client.get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"])
```

### Refactored File Structure (Phase 5)

```
src/
├── domain/
│   └── ports/
│       └── observability_port.py          # IObservabilityHandler
└── infrastructure/
    ├── observability/
    │   └── langfuse_adapter.py            # LangfuseObservabilityHandler
    └── secrets/
        └── secrets_manager_adapter.py     # SecretsManagerAdapter (bootstrap moved here)
```

> **Removed:** `_load_langfuse_secrets()` from `agent_handler.py` — this logic belongs in `SecretsManagerAdapter`, called once from the entry point's startup routine, not interleaved with handler logic.

---

## Phase 6 — FastAPI Endpoint & AgentCore Deployment

### Audit Summary

The plan's `src/app.py` and `src/agent_handler.py` are entry points (Infrastructure adapters). The problem is that they currently contain application logic: JWT decoding, Langfuse config assembly, and streaming orchestration. These must be delegated to the Application layer via a `RunAgentUseCase`.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. Cognito JWKS fetch (`httpx.get`) | `src/auth/cognito.py` | **Infrastructure** | HTTP call is infrastructure |
| A. JWT `decode()` call | `src/auth/cognito.py` | **Infrastructure** | crypto lib usage is infrastructure |
| A. `validate_cognito_token` logic | `src/auth/cognito.py` | **Infrastructure** | Implements `ITokenValidator` |
| A. `get_current_user` FastAPI dependency | `src/app.py` | **Infrastructure (entrypoint)** | FastAPI Depends wiring is adapter code |
| B. `QueryRequest` Pydantic model | `src/app.py` | **Infrastructure (entrypoint)** | Request/response schemas are API layer |
| B. `event_stream()` async generator | `src/app.py` | **Infrastructure (entrypoint)** | SSE formatting is a presentation adapter |
| B. Wiring `config["callbacks"]`, `recursion_limit` | `src/app.py` | **Application** | These belong in `RunAgentUseCase` |
| B. `/health` route | `src/app.py` | **Infrastructure (entrypoint)** | HTTP health check endpoint |
| C. `_load_langfuse_secrets()` | `src/agent_handler.py` | **Infrastructure** | Move to `SecretsManagerAdapter` startup |
| C. `BedrockAgentCoreApp()` + `@app.entrypoint` | `src/agent_handler.py` | **Infrastructure (entrypoint)** | AgentCore SDK wiring is an adapter |
| C. JWT base64 decode inside handler | `src/agent_handler.py` | **Infrastructure** | Delegates to `ITokenValidator` |
| C. `graph.astream(...)` loop + yielding | `src/agent_handler.py` | **Application** | Streaming orchestration belongs in `RunAgentUseCase` |

### Required Interfaces / Contracts

```python
# src/application/use_cases/run_agent.py
from typing import AsyncGenerator, Any
from src.domain.ports.llm_port import ILanguageModel
from src.domain.ports.observability_port import IObservabilityHandler

class RunAgentUseCase:
    """Orchestrates a single agent invocation and streams results."""

    def __init__(self, graph, observability: IObservabilityHandler):
        self._graph = graph
        self._observability = observability

    async def execute(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        from langchain_core.messages import HumanMessage
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
```

The entry points (`fastapi_app.py`, `agentcore_handler.py`) are thin: they resolve dependencies, call `RunAgentUseCase.execute()`, and format the output for their respective transport (SSE / AgentCore streaming).

### Refactored File Structure (Phase 6)

```
src/
├── application/
│   └── use_cases/
│       └── run_agent.py                    # RunAgentUseCase (streaming orchestration)
└── infrastructure/
    ├── auth/
    │   └── cognito_validator.py            # CognitoTokenValidator implements ITokenValidator
    └── entrypoints/
        ├── fastapi_app.py                  # FastAPI app (thin adapter: auth → RunAgentUseCase → SSE)
        └── agentcore_handler.py            # AgentCore handler (thin: secret bootstrap → RunAgentUseCase → yield)
```

> **Removed:** `src/app.py` (renamed to `src/infrastructure/entrypoints/fastapi_app.py`).
> **Removed:** `src/agent_handler.py` (renamed to `src/infrastructure/entrypoints/agentcore_handler.py`).
> **Removed:** `src/auth/cognito.py` (renamed to `src/infrastructure/auth/cognito_validator.py` and now implements `ITokenValidator`).

---

## Phase 7 — UAT Notebook & Documentation

### Audit Summary

The notebook and README are external-facing deliverables. They are Infrastructure/Presentation artifacts and do not introduce new architectural violations. However, the notebook currently hard-codes endpoint payloads (`{"prompt": "..."}` vs `{"query": "..."}`) and mixes configuration values with code — both are presentation-layer concerns that should be contained in the configuration cell.

### Task Breakdown

| Task | Current placement (plan) | Correct layer | Notes |
|---|---|---|---|
| A. Jupyter notebook configuration cell | `notebooks/demo.ipynb` | **Infrastructure / Presentation** | Correct — stays in `notebooks/` |
| A. Cognito `initiate_auth` call | `notebooks/demo.ipynb` | **Infrastructure / Presentation** | External auth call is infrastructure in the notebook context |
| A. `query_agent()` streaming helper | `notebooks/demo.ipynb` | **Infrastructure / Presentation** | HTTP streaming client is a presentation adapter |
| A. 5 UAT query cells | `notebooks/demo.ipynb` | **Infrastructure / Presentation** | Correct — stays in `notebooks/` |
| A. Langfuse trace retrieval | `notebooks/demo.ipynb` | **Infrastructure / Presentation** | Calls Langfuse API directly — acceptable in a presentation notebook |
| B. README deployment instructions | `README.md` | **Infrastructure / Presentation** | Correct — stays in root |
| B. Architecture diagram | `README.md` | **Infrastructure / Presentation** | Correct |

### Recommended Improvements

- Unify the payload key: use `prompt` everywhere (both `fastapi_app.py` and `agentcore_handler.py`) to eliminate the `query` vs `prompt` confusion documented in the phase plan.
- Extract the `query_agent` helper to a standalone `notebooks/helpers.py` module so it can be reused and is not duplicated between notebook cells.
- The notebook should document that it calls the **Application layer's contract** (`RunAgentUseCase` interface shape), not the internal graph API — making it robust to future Infrastructure changes.

### Refactored File Structure (Phase 7)

```
.
├── README.md
├── notebooks/
│   ├── demo.ipynb           # UAT notebook (no structural change)
│   └── helpers.py           # NEW — query_agent helper extracted here
└── docs/
    ├── phases/              # Phase plans (unchanged)
    └── CleanArchitecture.md # This document
```

---

## Consolidated Refactored File Structure

The complete proposed layout after applying all phase audits:

```
src/
├── domain/
│   ├── entities/
│   │   ├── stock_price.py              # StockPrice, HistoricalRecord, HistoricalPrices
│   │   └── document_chunk.py           # DocumentChunk
│   └── ports/
│       ├── stock_data_port.py          # IStockDataProvider
│       ├── document_loader_port.py     # IDocumentLoader
│       ├── vector_store_port.py        # IVectorStore
│       ├── llm_port.py                 # ILanguageModel
│       ├── secret_store_port.py        # ISecretStore
│       ├── token_validator_port.py     # ITokenValidator
│       └── observability_port.py      # IObservabilityHandler
│
├── application/
│   ├── agent/
│   │   ├── state.py                    # AgentState TypedDict
│   │   ├── prompts.py                  # SYSTEM_PROMPT constant
│   │   └── graph.py                    # ReAct graph (depends on ILanguageModel, injected)
│   ├── use_cases/
│   │   ├── get_realtime_price.py       # GetRealtimeStockPriceUseCase
│   │   ├── get_historical_prices.py    # GetHistoricalStockPricesUseCase
│   │   ├── retrieve_documents.py       # RetrieveFinancialDocumentsUseCase
│   │   └── run_agent.py                # RunAgentUseCase (streaming orchestration)
│   └── services/
│       └── knowledge_ingestor.py       # IngestDocumentsService (chunking + pipeline)
│
└── infrastructure/
    ├── stock_data/
    │   └── yfinance_adapter.py         # YFinanceStockDataProvider → IStockDataProvider
    ├── knowledge_base/
    │   ├── pdf_loader.py               # PDFDocumentLoader → IDocumentLoader
    │   ├── faiss_vector_store.py       # FAISSVectorStore → IVectorStore
    │   └── ingest.py                   # CLI: calls IngestDocumentsService
    ├── llm/
    │   └── bedrock_adapter.py          # BedrockChatAdapter → ILanguageModel
    ├── observability/
    │   └── langfuse_adapter.py         # LangfuseObservabilityHandler → IObservabilityHandler
    ├── auth/
    │   └── cognito_validator.py        # CognitoTokenValidator → ITokenValidator
    ├── secrets/
    │   └── secrets_manager_adapter.py  # SecretsManagerAdapter → ISecretStore
    └── entrypoints/
        ├── fastapi_app.py              # FastAPI HTTP server (local dev)
        ├── agentcore_handler.py        # AgentCore BedrockAgentCoreApp entry point
        └── tool_registry.py            # @tool wrappers that bind use-cases to LangChain

infrastructure/          # Terraform (cloud provisioning — outside src/)
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── cognito.tf
│   ├── iam.tf
│   ├── ecr.tf
│   └── secrets.tf

notebooks/
│   ├── demo.ipynb
│   └── helpers.py

vectorstore/             # Pre-built FAISS index
data/
│   └── pdfs/            # Downloaded PDFs (gitignored)
```

---

## Dependency Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Infrastructure (entrypoints, adapters, SDKs, AWS, HTTP)    │
│                                                             │
│  fastapi_app.py          ─────────────────────────────┐    │
│  agentcore_handler.py    ──────────────────────────┐  │    │
│  yfinance_adapter.py     ──────────────────────┐   │  │    │
│  bedrock_adapter.py      ──────────────────┐   │   │  │    │
│  faiss_vector_store.py   ──────────────┐   │   │   │  │    │
│  langfuse_adapter.py     ──────────┐   │   │   │   │  │    │
│  cognito_validator.py    ──────┐   │   │   │   │   │  │    │
│  secrets_manager_adapter.py ─┐ │   │   │   │   │   │  │    │
└─────────────────────────────┼─┼───┼───┼───┼───┼───┼──┼────┘
                              │ │   │   │   │   │   │  │
                              ▼ ▼   ▼   ▼   ▼   ▼   ▼  ▼
┌─────────────────────────────────────────────────────────────┐
│  Application (use-cases, agent orchestration, services)     │
│                                                             │
│  RunAgentUseCase                                            │
│  GetRealtimeStockPriceUseCase                               │
│  GetHistoricalStockPricesUseCase                            │
│  RetrieveFinancialDocumentsUseCase                          │
│  IngestDocumentsService                                     │
│  graph.py (ReAct loop, depends on ILanguageModel port)      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Domain (entities, ports — zero external dependencies)      │
│                                                             │
│  StockPrice, HistoricalPrices, DocumentChunk (entities)     │
│  IStockDataProvider, IVectorStore, ILanguageModel,          │
│  IDocumentLoader, ISecretStore, ITokenValidator,            │
│  IObservabilityHandler  (ports / abstract interfaces)       │
└─────────────────────────────────────────────────────────────┘
```

All arrows point **inward**: Infrastructure depends on Application and Domain; Application depends only on Domain; Domain has no outward dependencies.

---

## Summary of Key Changes per Phase

| Phase | Key Violation Found | Fix Applied |
|---|---|---|
| 1 — Infra & Auth | JWT validation placed in `src/auth/` without abstraction | Added `ITokenValidator` port; `CognitoTokenValidator` adapter in infrastructure |
| 1 — Infra & Auth | Secret fetching entangled with entry point code | Added `ISecretStore` port; `SecretsManagerAdapter` in infrastructure |
| 2 — Finance Tools | Domain entities and yfinance SDK calls in same file | Split into `StockPrice` entity (domain), use-cases (application), `YFinanceStockDataProvider` adapter (infrastructure) |
| 2 — Finance Tools | `@tool` decorators coupling domain logic to LangChain | `@tool` wrappers moved to `infrastructure/entrypoints/tool_registry.py` |
| 3 — Knowledge Base | PDF loading, chunking, embedding, and FAISS all in one module | Split into `IDocumentLoader` + `IVectorStore` ports, `IngestDocumentsService` use-case, and concrete adapters |
| 4 — LangGraph Agent | LLM instantiation (`ChatBedrock`) inside `graph.py` | Added `ILanguageModel` port; `BedrockChatAdapter` injected at startup |
| 5 — Observability | `CallbackHandler` + secret bootstrap embedded in entry points | Added `IObservabilityHandler` port; `LangfuseObservabilityHandler` adapter; bootstrap moved to `SecretsManagerAdapter` |
| 6 — FastAPI / AgentCore | Streaming orchestration and JWT decoding in entry point files | Streaming logic moved to `RunAgentUseCase`; entry points are now thin adapters |
| 7 — UAT Notebook | Minor: `query` vs `prompt` payload key inconsistency | Unified on `prompt`; `query_agent` helper extracted to `notebooks/helpers.py` |
