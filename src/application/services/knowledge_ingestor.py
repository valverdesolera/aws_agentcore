"""
Application service: orchestrates the full knowledge base ingestion pipeline.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.

Business decisions owned here:
  - CHUNK_SIZE / CHUNK_OVERLAP: what constitutes a good retrieval chunk.
  - Ingestion flow: load → embed → persist.

Infrastructure adapters (IDocumentLoader, IVectorStore) are injected; no
imports from langchain, faiss, boto3, or any other external library appear here.
"""

from src.domain.entities.document_chunk import DocumentChunk
from src.domain.ports.document_loader_port import IDocumentLoader
from src.domain.ports.vector_store_port import IVectorStore


class IngestDocumentsService:
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    def __init__(self, loader: IDocumentLoader, vector_store: IVectorStore) -> None:
        self._loader = loader
        self._vector_store = vector_store

    def ingest(self, sources: list[str], persist_path: str) -> int:
        """Run the full ingestion pipeline for a list of PDF URLs or local paths.

        Args:
            sources:      List of PDF URLs or absolute local file paths.
            persist_path: Directory where the vector store index will be saved.

        Returns:
            Total number of chunks indexed.
        """
        all_chunks: list[DocumentChunk] = []
        for source in sources:
            chunks = self._loader.load(source)
            all_chunks.extend(chunks)

        self._vector_store.add_documents(all_chunks)
        self._vector_store.persist(persist_path)
        return len(all_chunks)
