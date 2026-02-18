"""
Port (interface) for JWT token validators.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.
Infrastructure adapters (e.g. CognitoTokenValidator) must implement this interface.
"""

from abc import ABC, abstractmethod


class ITokenValidator(ABC):
    @abstractmethod
    def validate(self, token: str) -> dict:
        """Validate a JWT token and return its decoded claims.

        Raises:
            ValueError: if the token is invalid, expired, or fails audience/issuer checks.
        """
        ...
