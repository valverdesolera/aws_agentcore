"""
Infrastructure adapter: FAISS + Bedrock Titan Embeddings → IVectorStore.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.

All FAISS and BedrockEmbeddings details are confined here.
DocumentChunk ↔ langchain Document conversion happens in this adapter so
the rest of the codebase never imports langchain_community or faiss directly.
"""

import os

from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from src.domain.entities.document_chunk import DocumentChunk
from src.domain.ports.vector_store_port import IVectorStore


class FAISSVectorStore(IVectorStore):
    """FAISS vector store backed by Amazon Bedrock Titan Text Embeddings v2."""

    _EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

    def __init__(self) -> None:
        self._embedding = BedrockEmbeddings(
            model_id=self._EMBEDDING_MODEL_ID,
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
        self._store: FAISS | None = None

    # ------------------------------------------------------------------
    # IVectorStore interface
    # ------------------------------------------------------------------

    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        """Embed all chunks and build the in-memory FAISS index."""
        print(f"Embedding {len(chunks)} chunks with Bedrock Titan ...")
        lc_docs = [self._to_lc_doc(chunk) for chunk in chunks]
        self._store = FAISS.from_documents(lc_docs, self._embedding)

    def persist(self, path: str) -> None:
        """Serialize the FAISS index and metadata to *path*."""
        if self._store is None:
            raise RuntimeError("No documents indexed — call add_documents() first.")
        os.makedirs(path, exist_ok=True)
        self._store.save_local(path)
        print(f"FAISS index saved to {path}/")

    def similarity_search(self, query: str, k: int = 5) -> list[DocumentChunk]:
        """Return the *k* most semantically similar chunks for *query*."""
        if self._store is None:
            raise RuntimeError("Vector store not loaded — call FAISSVectorStore.load() first.")
        results = self._store.similarity_search(query, k=k)
        return [self._from_lc_doc(doc) for doc in results]

    @classmethod
    def load(cls, path: str) -> "FAISSVectorStore":
        """Reconstruct the index from a previously persisted directory.

        allow_dangerous_deserialization=True is required because FAISS uses pickle
        internally. Safe here: we only ever load indexes we built ourselves.
        """
        instance = cls()
        instance._store = FAISS.load_local(
            path,
            instance._embedding,
            allow_dangerous_deserialization=True,
        )
        return instance

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_lc_doc(chunk: DocumentChunk) -> Document:
        return Document(
            page_content=chunk.content,
            metadata={
                "source_file": chunk.source_file,
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
            },
        )

    @staticmethod
    def _from_lc_doc(doc: Document) -> DocumentChunk:
        return DocumentChunk(
            content=doc.page_content,
            source_file=doc.metadata.get("source_file", "Unknown"),
            page=int(doc.metadata.get("page", 0)),
            chunk_id=int(doc.metadata.get("chunk_id", 0)),
        )
