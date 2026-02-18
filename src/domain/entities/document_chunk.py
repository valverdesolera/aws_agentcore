"""
Domain entity for a chunked financial document section.
See docs/CleanArchitecture.md — Phase 3 for the architectural rationale.
Zero external dependencies — pure Python dataclass only.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source_file: str
    page: int
    chunk_id: int
