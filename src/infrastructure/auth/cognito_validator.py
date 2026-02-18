"""
Infrastructure adapter: AWS Cognito JWKS → ITokenValidator.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.

Validates RS256-signed Cognito ID tokens by fetching the public JWKS endpoint
and verifying signature, audience, issuer, and token_use claim.
JWKS are cached per-process via functools.lru_cache to avoid repeated HTTP calls.
"""

from functools import lru_cache

import httpx
from jose import JWTError, jwt

from src.domain.ports.token_validator_port import ITokenValidator


class CognitoTokenValidator(ITokenValidator):
    """Validates Cognito ID tokens against the user pool's public JWKS."""

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        region: str = "us-east-1",
    ) -> None:
        self._client_id = client_id
        self._jwks_url = (
            f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
            "/.well-known/jwks.json"
        )
        self._issuer = (
            f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        )

    @lru_cache(maxsize=1)
    def _get_jwks(self) -> dict:
        response = httpx.get(self._jwks_url, timeout=10)
        response.raise_for_status()
        return response.json()

    def validate(self, token: str) -> dict:
        """Decode and validate a Cognito ID token.

        Raises:
            ValueError: on any validation failure (bad signature, expiry,
                        wrong audience/issuer, wrong token_use).
        """
        try:
            jwks = self._get_jwks()
            kid = jwt.get_unverified_header(token).get("kid")
            rsa_key = next(
                (key for key in jwks.get("keys", []) if key["kid"] == kid),
                None,
            )
            if not rsa_key:
                raise ValueError("Matching key not found in JWKS — token may be stale.")

            claims = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=self._issuer,
            )
            if claims.get("token_use") != "id":
                raise ValueError(
                    f"Invalid token_use: expected 'id', got {claims.get('token_use')!r}"
                )
            return claims
        except JWTError as exc:
            raise ValueError(f"Token validation failed: {exc}") from exc
