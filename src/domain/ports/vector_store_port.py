"""
Port (interface) for vector stores.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.
Infrastructure adapters (e.g. FAISSVectorStore) must implement this interface.
"""

from abc import ABC, abstractmethod

from src.domain.entities.document_chunk import DocumentChunk


class IVectorStore(ABC):
    @abstractmethod
    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        """Embed and index a list of document chunks."""
        ...

    @abstractmethod
    def persist(self, path: str) -> None:
        """Save the index to disk."""
        ...

    @abstractmethod
    def similarity_search(self, query: str, k: int = 5) -> list[DocumentChunk]:
        """Return the k most semantically similar chunks for a query."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "IVectorStore":
        """Reconstruct the index from a persisted path."""
        ...
