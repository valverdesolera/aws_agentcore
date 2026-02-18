"""
Infrastructure adapter: Amazon Bedrock (ChatBedrock) → ILanguageModel.
See docs/CleanArchitecture.md — Phase 4 for the architectural rationale.

All ChatBedrock / langchain_aws details are confined here.
bind_tools() returns a new BedrockChatAdapter wrapping the tool-bound Runnable
so the ILanguageModel contract is preserved throughout.
"""

import os
from typing import Any

from langchain_aws import ChatBedrock

from src.domain.ports.llm_port import ILanguageModel


class BedrockChatAdapter(ILanguageModel):
    """Wraps ChatBedrock and exposes the ILanguageModel interface."""

    MODEL_ID = "us.amazon.nova-pro-v1:0"

    def __init__(self, _runnable: Any = None) -> None:
        """
        Args:
            _runnable: Optional pre-configured Runnable (used internally by
                       bind_tools to wrap the tool-bound model without re-constructing
                       ChatBedrock). Pass nothing for normal instantiation.
        """
        if _runnable is not None:
            self._llm = _runnable
        else:
            self._llm = ChatBedrock(
                model=self.MODEL_ID,
                model_kwargs={"temperature": 0.0},
                region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            )

    def invoke(self, messages: list[Any]) -> Any:
        return self._llm.invoke(messages)

    def bind_tools(self, tools: list) -> "BedrockChatAdapter":
        """Return a new adapter that has the given tools bound for function-calling."""
        return BedrockChatAdapter(_runnable=self._llm.bind_tools(tools))
