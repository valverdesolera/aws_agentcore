"""
Use-case: semantic search over the financial knowledge base.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.
Depends only on Domain ports and entities — no infrastructure imports.
"""

from src.domain.ports.vector_store_port import IVectorStore


class RetrieveFinancialDocumentsUseCase:
    def __init__(self, vector_store: IVectorStore) -> None:
        self._vector_store = vector_store

    def execute(self, query: str, k: int = 5) -> str:
        """Search the vector store and return formatted passages.

        Args:
            query: Natural-language search query.
            k:     Number of top chunks to retrieve.

        Returns:
            Newline-delimited passages with source metadata, or an empty string
            if the vector store returns no results.
        """
        chunks = self._vector_store.similarity_search(query, k=k)
        if not chunks:
            return ""
        passages = [
            f"[Source: {c.source_file}, Page: {c.page}]\n{c.content}"
            for c in chunks
        ]
        return "\n\n---\n\n".join(passages)
