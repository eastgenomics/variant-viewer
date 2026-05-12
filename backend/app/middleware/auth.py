"""API key authentication middleware for FastAPI routes."""
from __future__ import annotations

import json
import logging
import os
import secrets

import boto3
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_resolved_key: str | None = None


def _get_api_key() -> str:
    """Resolve the expected API key (lazy singleton).

    Resolution order:
    1. Cached value (already resolved this process lifetime).
    2. AWS Secrets Manager if ``API_KEY_SECRET_ARN`` is set.
    3. ``API_KEY`` environment variable.

    Raises RuntimeError if neither source is configured.
    """
    global _resolved_key
    if _resolved_key:
        return _resolved_key

    arn = os.environ.get("API_KEY_SECRET_ARN")
    if arn:
        region = os.environ.get("AWS_REGION", "eu-west-2")
        sm = boto3.client("secretsmanager", region_name=region)
        resp = sm.get_secret_value(SecretId=arn)
        secret = json.loads(resp["SecretString"])
        if "api_key" not in secret:
            raise RuntimeError(
                f"Secrets Manager secret {arn!r} must contain an 'api_key' field"
            )
        _resolved_key = secret["api_key"]
    else:
        _resolved_key = os.environ.get("API_KEY")

    if not _resolved_key:
        raise RuntimeError("API_KEY or API_KEY_SECRET_ARN must be set")

    return _resolved_key


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """FastAPI dependency: validate X-API-Key header.

    Raises HTTP 401 if the header is absent or does not match the resolved key.
    """
    expected = _get_api_key()
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


def _reset_resolved_key() -> None:
    """Test helper — reset cached key between tests."""
    global _resolved_key
    _resolved_key = None
