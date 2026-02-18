# Project Phase Structure

Phased breakdown of the take-home assessment in integration order. Each phase builds on the previous one to avoid blocked dependencies.

> **Detailed phase documents:** Each phase has a dedicated document in [`docs/phases/`](docs/phases/) with setup instructions, code samples, dependencies, and verification checklists.

| Phase | Document |
|---|---|
| 1 | [PHASE_1_INFRASTRUCTURE_AND_AUTH.md](docs/phases/PHASE_1_INFRASTRUCTURE_AND_AUTH.md) |
| 2 | [PHASE_2_FINANCE_TOOLS.md](docs/phases/PHASE_2_FINANCE_TOOLS.md) |
| 3 | [PHASE_3_KNOWLEDGE_BASE.md](docs/phases/PHASE_3_KNOWLEDGE_BASE.md) |
| 4 | [PHASE_4_LANGGRAPH_REACT_AGENT.md](docs/phases/PHASE_4_LANGGRAPH_REACT_AGENT.md) |
| 5 | [PHASE_5_LANGFUSE_OBSERVABILITY.md](docs/phases/PHASE_5_LANGFUSE_OBSERVABILITY.md) |
| 6 | [PHASE_6_FASTAPI_AGENTCORE_DEPLOYMENT.md](docs/phases/PHASE_6_FASTAPI_AGENTCORE_DEPLOYMENT.md) |
| 7 | [PHASE_7_UAT_NOTEBOOK_AND_DOCS.md](docs/phases/PHASE_7_UAT_NOTEBOOK_AND_DOCS.md) |

---

## Phase 1 — Infrastructure & Auth Foundation

**Goal:** Provision all cloud infrastructure so every subsequent phase has a stable, deployable target.

- [ ] Initialize Terraform project structure (providers, backend, variables, outputs)
- [ ] Provision **AWS Cognito User Pool** and App Client for user authorization
- [ ] Provision supporting AWS resources (IAM roles, ECR repository, networking/VPC if required)
- [ ] Provision **AWS AgentCore Runtime** environment via Terraform
- [ ] Store sensitive config (Cognito client secret, etc.) in AWS Secrets Manager or SSM Parameter Store
- [ ] Verify Terraform `plan` and `apply` succeed end-to-end with no manual steps

**Deliverable:** Fully provisioned AWS environment with Cognito auth and AgentCore Runtime ready to receive a container image.

---

## Phase 2 — Finance Tools (Core Agent Capabilities)

**Goal:** Build and unit-test the two finance tools in isolation before wiring them into the agent.

- [ ] Set up Python project structure (`pyproject.toml` / `requirements.txt`, virtual environment)
- [ ] Implement `retrieve_realtime_stock_price` tool using `yfinance`
- [ ] Implement `retrieve_historical_stock_price` tool using `yfinance`
- [ ] Write local unit tests for both tools to validate correct data retrieval and error handling

**Deliverable:** Two verified, standalone finance tools ready to be registered with the LangGraph agent.

---

## Phase 3 — Knowledge Base & Document Retrieval

**Goal:** Ingest the three Amazon financial PDFs and expose them as a retrieval tool for the agent.

- [ ] Download and parse the three Amazon financial PDFs:
  - Amazon 2024 Annual Report
  - AMZN Q3 2025 Earnings Release
  - AMZN Q2 2025 Earnings Release
- [ ] Set up a vector store / embedding pipeline for document chunking and indexing
- [ ] Implement a document retrieval tool (e.g., `retrieve_financial_documents`) compatible with LangGraph
- [ ] Validate retrieval accuracy with sample queries against the indexed documents

**Deliverable:** A working retrieval tool that can answer questions grounded in the three Amazon financial documents.

---

## Phase 4 — LangGraph ReAct Agent

**Goal:** Compose the finance tools and knowledge base retrieval tool into a single ReAct-style agent.

- [ ] Define the **LangGraph ReAct agent** graph with all three tools registered:
  - `retrieve_realtime_stock_price`
  - `retrieve_historical_stock_price`
  - Document retrieval tool
- [ ] Implement **streaming** via `.astream()` so all event responses are streamed token-by-token
- [ ] Test the agent locally against the five UAT queries:
  - What is the stock price for Amazon right now?
  - What were the stock prices for Amazon in Q4 last year?
  - Compare Amazon's recent stock performance to what analysts predicted in their reports
  - I'm researching AMZN — give me the current price and any relevant information about their AI business
  - What is the total amount of office space Amazon owned in North America in 2024?
- [ ] Verify the agent selects the correct tools for each query type

**Deliverable:** A fully functional LangGraph ReAct agent that streams responses and correctly combines live data with document-grounded answers.

---

## Phase 5 — Observability with Langfuse

**Goal:** Integrate Langfuse so every agent invocation is traced end-to-end.

- [ ] Create a **Langfuse cloud free-tier** account and project
- [ ] Integrate Langfuse tracing into the LangGraph agent (callbacks or SDK integration)
- [ ] Verify that traces, spans, and LLM calls are visible in the Langfuse dashboard
- [ ] Capture example trace screenshots for use in the UAT notebook

**Deliverable:** Full observability for every agent invocation, with Langfuse traces confirming tool usage and LLM calls.

---

## Phase 6 — FastAPI Endpoint & AgentCore Deployment

**Goal:** Wrap the agent in a FastAPI application, containerize it, and deploy it to AgentCore Runtime.

- [ ] Implement the **FastAPI** application with a streaming endpoint that:
  - Accepts user queries
  - Validates the incoming **Cognito JWT token** (authorization middleware)
  - Invokes the LangGraph agent and streams the response back via SSE or chunked transfer
- [ ] Write a `Dockerfile` for the FastAPI app
- [ ] Push the container image to ECR (integrate with Terraform or CI script)
- [ ] Deploy the container to **AWS AgentCore Runtime**
- [ ] Smoke-test the deployed endpoint end-to-end (auth → query → streamed response)

**Deliverable:** A live, secured, streaming FastAPI endpoint hosted on AgentCore Runtime.

---

## Phase 7 — UAT Notebook & Documentation

**Goal:** Produce all deliverables required for reviewer acceptance.

- [ ] Write a **Jupyter notebook** that:
  - Authenticates a user against the **Cognito user pool** and obtains a JWT token
  - Invokes the deployed endpoint for each of the five UAT queries
  - Displays streamed responses inline
  - Includes **screenshots or API responses showing Langfuse traces** for each invocation
- [ ] Write a clear **README** covering:
  - Architecture overview
  - Prerequisites (AWS account, Terraform, Docker, Python version)
  - Step-by-step deployment instructions (`terraform apply`, image push, AgentCore deploy)
  - How to run the UAT notebook
- [ ] Final review: confirm all acceptance criteria are met before submission

**Deliverable:** A complete, reviewer-executable notebook and deployment documentation.

---

## Dependency Graph (Summary)

```
Phase 1 (Infra & Auth)
    └── Phase 2 (Finance Tools)   ──┐
    └── Phase 3 (Knowledge Base)  ──┤
                                    ├── Phase 4 (LangGraph Agent)
                                    │       └── Phase 5 (Langfuse)
                                    │               └── Phase 6 (FastAPI + AgentCore Deploy)
                                    │                       └── Phase 7 (Notebook + Docs)
```

Phases 2 and 3 can be developed in parallel once Phase 1 is complete.
Phase 5 can be integrated incrementally during Phase 4.
