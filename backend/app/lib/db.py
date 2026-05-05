from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Generator
from urllib.parse import quote_plus

import boto3
import psycopg2
import psycopg2.extensions
import psycopg2.pool

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_secrets_resolved: bool = False


def _resolve_secrets() -> None:
    global _secrets_resolved
    if _secrets_resolved:
        return

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        region = os.environ.get("AWS_REGION", "eu-west-2")
        sm = boto3.client("secretsmanager", region_name=region)
        resp = sm.get_secret_value(SecretId=secret_arn)
        secret = json.loads(resp["SecretString"])
        required = {"username", "password", "host", "dbname"}
        missing = required - set(secret.keys())
        if missing:
            raise RuntimeError(f"DB secret {secret_arn} missing fields: {missing}")
        port = secret.get("port", 5432)
        os.environ["DATABASE_URL"] = (
            f"postgresql://{quote_plus(secret['username'])}:{quote_plus(secret['password'])}"
            f"@{secret['host']}:{port}/{quote_plus(secret['dbname'])}"
        )

    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL or DB_SECRET_ARN must be set")

    _secrets_resolved = True


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    _resolve_secrets()
    if _pool is None:
        conn_str = os.environ["DATABASE_URL"]
        kwargs: dict = {}
        if os.environ.get("APP_ENV") == "production":
            kwargs["sslmode"] = "require"
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=conn_str, **kwargs
        )
    return _pool


@contextmanager
def _get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return all rows as a list of dicts."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            return []


@contextmanager
def with_transaction() -> Generator[psycopg2.extensions.connection, None, None]:
    """BEGIN on enter, COMMIT on clean exit, ROLLBACK on exception."""
    with _get_connection() as conn:
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True


def _reset_pool() -> None:
    """Test helper — reset module-level pool and secrets state."""
    global _pool, _secrets_resolved
    _pool = None
    _secrets_resolved = False
