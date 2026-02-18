"""
Port (interface) for observability / tracing handlers.
See docs/CleanArchitecture.md — Phase 5 for the architectural rationale.
Infrastructure adapters (e.g. LangfuseObservabilityHandler) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Any


class IObservabilityHandler(ABC):
    @abstractmethod
    def as_callback(self) -> Any:
        """Return the framework-native callback object (e.g. a LangChain CallbackHandler)."""
        ...

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered telemetry data to the remote backend."""
        ...
