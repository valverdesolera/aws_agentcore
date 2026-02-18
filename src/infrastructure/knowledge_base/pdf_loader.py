"""
Infrastructure adapter: PDF (URL or path) → IDocumentLoader.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.

Responsibilities confined here:
  - HTTP download and local caching of PDF files.
  - PDF parsing via PyPDFLoader (LangChain community).
  - Text splitting via RecursiveCharacterTextSplitter.

Chunking parameters (CHUNK_SIZE / CHUNK_OVERLAP) are injected from
IngestDocumentsService so the business decision remains in the application layer.
"""

import os

import requests
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.domain.entities.document_chunk import DocumentChunk
from src.domain.ports.document_loader_port import IDocumentLoader


class PDFDocumentLoader(IDocumentLoader):
    """Downloads PDFs, parses pages, and returns pre-chunked DocumentChunk objects."""

    _DOWNLOAD_DIR = "data/pdfs"

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def load(self, source: str) -> list[DocumentChunk]:
        """Load a PDF from a URL or local path and return chunked DocumentChunks."""
        local_path = self._resolve(source)
        loader = PyPDFLoader(local_path)
        pages = loader.load()
        lc_chunks = self._splitter.split_documents(pages)
        return [
            DocumentChunk(
                content=chunk.page_content,
                source_file=os.path.basename(local_path),
                page=int(chunk.metadata.get("page", 0)),
                chunk_id=idx,
            )
            for idx, chunk in enumerate(lc_chunks)
        ]

    def _resolve(self, source: str) -> str:
        if source.startswith("http://") or source.startswith("https://"):
            return self._download(source)
        return source

    def _download(self, url: str) -> str:
        os.makedirs(self._DOWNLOAD_DIR, exist_ok=True)
        filename = url.split("/")[-1]
        local_path = os.path.join(self._DOWNLOAD_DIR, filename)
        if not os.path.exists(local_path):
            print(f"Downloading {filename} ...")
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            with open(local_path, "wb") as fh:
                fh.write(response.content)
            print(f"  Saved to {local_path}")
        return local_path
