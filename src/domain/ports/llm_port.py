"""
Port (interface) for language model providers.
See docs/CleanArchitecture.md — Phase 4 for the architectural rationale.
Infrastructure adapters (e.g. BedrockChatAdapter) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Any


class ILanguageModel(ABC):
    @abstractmethod
    def invoke(self, messages: list[Any]) -> Any:
        """Invoke the model synchronously and return a response message."""
        ...

    @abstractmethod
    def bind_tools(self, tools: list) -> "ILanguageModel":
        """Return a new model instance with the given tools bound for function-calling."""
        ...
