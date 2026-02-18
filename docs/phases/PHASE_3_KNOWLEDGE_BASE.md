# Phase 3 — Knowledge Base & Document Retrieval

> **Architecture reference:** Before writing or reviewing any code for this phase, consult
> [`docs/CleanArchitecture.md`](../CleanArchitecture.md).
> Key files for this phase:
> - **Domain:** `src/domain/entities/document_chunk.py`, `src/domain/ports/document_loader_port.py`, `src/domain/ports/vector_store_port.py`
> - **Application:** `src/application/use_cases/retrieve_documents.py`, `src/application/services/knowledge_ingestor.py`
> - **Infrastructure:** `src/infrastructure/knowledge_base/pdf_loader.py`, `src/infrastructure/knowledge_base/faiss_vector_store.py`, `src/infrastructure/knowledge_base/ingest.py`

## Summary

Ingest the three required Amazon financial PDFs, chunk and embed them into a FAISS vector store, and expose the result as a LangChain-compatible retrieval tool that the LangGraph agent can use. This enables the agent to answer document-grounded questions like "What is the total amount of office space Amazon owned in North America in 2024?"

> **Deployment model note:** Because the reviewer runs the notebook against your live cloud endpoint (not a local server), the FAISS index must be available inside the deployed AgentCore Runtime container. The recommended approach is to build the index locally with the `ingest.py` script, commit the persisted index to the repo (or upload it to S3), and include it in the container image at deploy time. See Implementation Notes below for details.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `langchain-community` | FAISS vector store, PDF loader |
| `langchain-openai` or `langchain-aws` | Embedding model (OpenAI or Bedrock) |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter` |
| `faiss-cpu` | FAISS vector store (CPU version) |
| `pypdf` or `pymupdf` | PDF parsing |
| `requests` | HTTP client for downloading PDFs |
| Phase 1 | Not strictly required — can develop locally |

---

## Setup

### 1. Install Dependencies

```bash
pip install langchain-community langchain-text-splitters faiss-cpu pypdf requests langchain-openai
# OR for AWS Bedrock embeddings:
pip install langchain-aws
```

### 2. Project File Structure

```
src/
├── knowledge_base/
│   ├── __init__.py
│   ├── ingest.py              # PDF download, chunking, embedding, index creation
│   └── retriever.py           # Retrieval tool for LangGraph
├── data/
│   └── pdfs/                  # Downloaded PDFs (gitignored)
└── vectorstore/               # Persisted FAISS index — committed to repo or uploaded to S3
```

> **No unit tests** are required for this phase. Validation is done manually by running sample queries against the retriever.

### 3. Source Documents

| Document | URL |
|---|---|
| Amazon 2024 Annual Report | `https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf` |
| AMZN Q3 2025 Earnings Release | `https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf` |
| AMZN Q2 2025 Earnings Release | `https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf` |

---

## Requirements

### A. PDF Ingestion

Download and parse the three PDFs into LangChain `Document` objects.

```python
import os
import requests
from langchain_community.document_loaders import PyPDFLoader

PDF_URLS = {
    "Amazon-2024-Annual-Report": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf",
    "AMZN-Q3-2025-Earnings-Release": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf",
    "AMZN-Q2-2025-Earnings-Release": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf",
}

def download_pdfs(output_dir: str = "data/pdfs") -> list[str]:
    """Download PDFs if not already present. Returns list of file paths."""
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for name, url in PDF_URLS.items():
        path = os.path.join(output_dir, f"{name}.pdf")
        if not os.path.exists(path):
            response = requests.get(url)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
        paths.append(path)
    return paths

def load_documents(pdf_paths: list[str]) -> list:
    """Load all PDFs into LangChain Document objects."""
    all_docs = []
    for path in pdf_paths:
        loader = PyPDFLoader(path)
        docs = loader.load()
        # Add source metadata
        for doc in docs:
            doc.metadata["source_file"] = os.path.basename(path)
        all_docs.extend(docs)
    return all_docs
```

---

### B. Chunking

Split documents into overlapping chunks suitable for embedding and retrieval.

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_documents(documents: list, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """Split documents into chunks for embedding."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = text_splitter.split_documents(documents)

    # Add chunk index metadata
    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = idx

    return chunks
```

**Tuning guidelines:**
- `chunk_size=1000` with `chunk_overlap=200` is a good starting point for financial documents
- Larger chunks preserve more context but reduce retrieval precision
- Financial tables and figures may require special handling

---

### C. Embedding & FAISS Index

Create embeddings and store them in a FAISS vector store.

**Option 1: OpenAI Embeddings**

```python
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

def create_vectorstore(chunks: list, persist_dir: str = "vectorstore") -> FAISS:
    """Create FAISS vector store from document chunks."""
    embedding = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = FAISS.from_documents(chunks, embedding)

    # Persist to disk for reuse
    vectorstore.save_local(persist_dir)
    return vectorstore

def load_vectorstore(persist_dir: str = "vectorstore") -> FAISS:
    """Load a previously persisted FAISS vector store."""
    embedding = OpenAIEmbeddings(model="text-embedding-3-small")
    # allow_dangerous_deserialization=True is required because FAISS uses pickle.
    # SECURITY: Only load indexes you have built yourself — pickle allows arbitrary code execution.
    return FAISS.load_local(persist_dir, embedding, allow_dangerous_deserialization=True)
```

**Option 2: AWS Bedrock Embeddings (to keep everything on AWS)**

```python
from langchain_aws import BedrockEmbeddings

embedding = BedrockEmbeddings(
    model_id="amazon.titan-embed-text-v2:0",
    region_name="us-east-1",
)
```

---

### D. Retrieval Tool

Expose the vector store as a LangChain tool for LangGraph.

```python
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS


def create_retrieval_tool(vectorstore: FAISS):
    """Create a document retrieval tool from the vector store."""

    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    @tool
    def retrieve_financial_documents(query: str) -> str:
        """Search Amazon's financial documents (Annual Report 2024, Q2 and Q3 2025 Earnings Releases)
        for information relevant to the query.

        Use this tool when you need to answer questions about Amazon's financial data,
        business operations, earnings, revenue, office space, AI business, analyst
        predictions, or any other information that would be found in their official
        financial filings and reports.

        Args:
            query: The search query to find relevant financial document sections.

        Returns:
            Relevant text passages from Amazon's financial documents with source metadata.
        """
        docs = retriever.invoke(query)
        results = []
        for doc in docs:
            source = doc.metadata.get("source_file", "Unknown")
            page = doc.metadata.get("page", "N/A")
            results.append(f"[Source: {source}, Page: {page}]\n{doc.page_content}")
        return "\n\n---\n\n".join(results)

    return retrieve_financial_documents
```

**Reference:**
- LangChain FAISS integration: https://python.langchain.com/docs/integrations/vectorstores/faiss/
- LangChain PDF loader: https://python.langchain.com/docs/integrations/document_loaders/pypdf/

---

## Implementation Notes

1. **Embedding cost.** The Amazon 2024 Annual Report is a large document (~100+ pages). With `text-embedding-3-small` at $0.00002/1K tokens, expect well under $0.05 for the full set. Bedrock Titan embeddings have comparable pricing.

2. **Cloud deployment of the FAISS index.** Because the endpoint is cloud-hosted and accessed by the reviewer remotely, the FAISS index must be available inside the AgentCore Runtime container at runtime. Two options:

   **Option A (Recommended) — Bundle in the container:**
   Run `ingest.py` locally once, commit the `vectorstore/` directory to the repo (the index files are binary, ~10-50MB), and include them in the deployment. AgentCore's `direct_code_deploy` mode packages the working directory automatically:
   ```bash
   python -m src.knowledge_base.ingest   # run once locally
   # vectorstore/ is now populated
   agentcore deploy                       # bundles vectorstore/ in the deployment
   ```

   **Option B — Download from S3 at startup:**
   Upload the persisted index to an S3 bucket and download it at container startup. Add a startup hook in `agent_handler.py`:
   ```python
   import boto3, os
   s3 = boto3.client("s3")
   s3.download_file("my-bucket", "vectorstore/index.faiss", "vectorstore/index.faiss")
   s3.download_file("my-bucket", "vectorstore/index.pkl", "vectorstore/index.pkl")
   ```

3. **Ingestion script.** Run this once locally before deploying:

   ```bash
   python -m src.knowledge_base.ingest
   ```

4. **Metadata preservation.** Keep `source_file` and `page` number in each chunk's metadata so the agent can cite sources in its responses.

5. **Alternative: Amazon Bedrock Knowledge Bases.** AWS offers fully managed knowledge bases via Bedrock (with S3 ingestion and OpenSearch Serverless as the vector store). This would eliminate the need to manage the FAISS index in the container. It is a valid alternative if preferred, but adds Terraform complexity (S3 bucket, Bedrock KB resource, IAM policies). The FAISS approach is simpler for this scope.

---

## Verification Checklist

- [ ] All three PDFs download successfully
- [ ] PDF parsing produces non-empty Document lists for each file
- [ ] Chunking produces reasonable chunk sizes (inspect a few samples)
- [ ] FAISS index is created and persisted to disk
- [ ] `retrieve_financial_documents("Amazon AI business")` returns relevant passages
- [ ] `retrieve_financial_documents("office space North America 2024")` returns data from the Annual Report
- [ ] `retrieve_financial_documents("Q3 2025 earnings")` returns data from the Q3 Earnings Release
- [ ] The retrieval tool is compatible with `llm.bind_tools([...])`
