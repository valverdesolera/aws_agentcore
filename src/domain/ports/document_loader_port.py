"""
Port (interface) for document loaders.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.
Infrastructure adapters (e.g. PDFDocumentLoader) must implement this interface.
"""

from abc import ABC, abstractmethod

from src.domain.entities.document_chunk import DocumentChunk


class IDocumentLoader(ABC):
    @abstractmethod
    def load(self, source: str) -> list[DocumentChunk]:
        """Load and chunk a document from a URL or local path."""
        ...
