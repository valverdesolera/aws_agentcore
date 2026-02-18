"""
CLI entry point for the knowledge base ingestion pipeline.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.

This script is the Composition Root for the ingestion use-case: it wires
infrastructure adapters (PDFDocumentLoader, FAISSVectorStore) to the
IngestDocumentsService and triggers the pipeline.

Run once locally before deploying:

    export AWS_PROFILE=<your-profile>
    export AWS_DEFAULT_REGION=us-east-1
    python -m src.infrastructure.knowledge_base.ingest
"""

from src.application.services.knowledge_ingestor import IngestDocumentsService
from src.infrastructure.knowledge_base.faiss_vector_store import FAISSVectorStore
from src.infrastructure.knowledge_base.pdf_loader import PDFDocumentLoader

PDF_SOURCES = [
    "https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf",
    "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf",
    "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf",
]

VECTORSTORE_DIR = "vectorstore"


def main() -> None:
    loader = PDFDocumentLoader(
        chunk_size=IngestDocumentsService.CHUNK_SIZE,
        chunk_overlap=IngestDocumentsService.CHUNK_OVERLAP,
    )
    vector_store = FAISSVectorStore()
    service = IngestDocumentsService(loader=loader, vector_store=vector_store)

    total = service.ingest(sources=PDF_SOURCES, persist_path=VECTORSTORE_DIR)
    print(f"\nIngestion complete — {total} chunks indexed in '{VECTORSTORE_DIR}/'.")


if __name__ == "__main__":
    main()
