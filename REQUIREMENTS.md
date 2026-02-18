# Take Home Assessment - Teilur

## Summary

Build an AI agent solution on AWS that exposes a FastAPI endpoint via AWS AgentCore Runtime. The agent enables users to query real-time and historical stock prices and receive streamed responses. The solution must integrate a knowledge base with Amazon financial documents, use LangGraph for ReAct-style agent orchestration, and be fully secured via AWS Cognito. All infrastructure must be provisioned with Terraform, and observability must be configured through Langfuse.

---

## Requirements

### AWS Services (Minimum)

- **AWS AgentCore** — hosts the FastAPI runtime
- **AWS Cognito** — handles inbound user authorization

---

### Backend

- [ ] Written in **Python**
- [ ] **AgentCore Runtime** hosted via **FastAPI**
- [ ] **AWS Cognito user pool** configured for inbound user authorization
- [ ] **Langfuse** (cloud free tier) configured for observability
- [ ] **LangGraph** used for agent orchestration (**ReAct type agent**)
- [ ] **Knowledge base** with document retrieval from the following PDFs:
  - Amazon 2024 Annual Report: `https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf`
  - AMZN Q3 2025 Earnings Release: `https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf`
  - AMZN Q2 2025 Earnings Release: `https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf`
- [ ] Minimum **2 finance tools** for stock retrieval using the `yfinance` API:
  - `retrieve_realtime_stock_price`
  - `retrieve_historical_stock_price`
- [ ] **Streaming** events via `.astream()`
  - Reference: https://langchain-ai.github.io/langgraph/how-tos/streaming/#filter-by-llm-invocation
- [ ] **Infrastructure written in Terraform**
- [ ] All event responses must be **streamed**

---

### User Acceptance Criteria

- [ ] Source code in a **repository** with a clear **README** explaining how to deploy the infrastructure
- [ ] A **Jupyter notebook** demonstrating invocation of the deployed endpoint (executable by the review team) covering the following queries:
  - What is the stock price for Amazon right now?
  - What were the stock prices for Amazon in Q4 last year?
  - Compare Amazon's recent stock performance to what analysts predicted in their reports
  - I'm researching AMZN — give me the current price and any relevant information about their AI business
  - What is the total amount of office space Amazon owned in North America in 2024?
- [ ] Notebook must contain **screenshots or API responses showing Langfuse traces**
- [ ] Notebook must demonstrate **user authentication from the Cognito user pool**
