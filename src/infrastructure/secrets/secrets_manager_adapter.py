"""
Infrastructure adapter: AWS Secrets Manager → ISecretStore.
See docs/CleanArchitecture.md — Phase 6 for the architectural rationale.

load_into_env() is called once at AgentCore container startup (before any SDK
that reads LANGFUSE_* env vars is imported) so secrets are available process-wide.
"""

import json
import os

import boto3

from src.domain.ports.secret_store_port import ISecretStore


class SecretsManagerAdapter(ISecretStore):
    """Fetches and deserializes secrets from AWS Secrets Manager."""

    def __init__(self, region: str | None = None) -> None:
        self._client = boto3.client(
            "secretsmanager",
            region_name=region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )

    def get_secret(self, secret_arn: str) -> dict:
        """Fetch and deserialize a JSON secret by ARN."""
        response = self._client.get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"])

    def load_into_env(self, secret_arn: str) -> None:
        """Inject all key-value pairs of a JSON secret into os.environ.

        Must be called before any library that reads env vars at import time
        (e.g. langfuse.langchain.CallbackHandler reads LANGFUSE_SECRET_KEY).
        """
        secrets = self.get_secret(secret_arn)
        for key, value in secrets.items():
            os.environ[key] = str(value)
