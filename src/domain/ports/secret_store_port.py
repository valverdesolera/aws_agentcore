"""
Port (interface) for secret stores.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.
Infrastructure adapters (e.g. SecretsManagerAdapter) must implement this interface.
"""

from abc import ABC, abstractmethod


class ISecretStore(ABC):
    @abstractmethod
    def get_secret(self, secret_arn: str) -> dict:
        """Fetch and deserialize a secret by ARN. Returns the key-value pairs."""
        ...
