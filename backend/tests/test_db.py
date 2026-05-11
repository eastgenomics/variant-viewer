import os
import pytest
from unittest.mock import MagicMock, patch

import app.lib.db as db_module


@pytest.fixture(autouse=True)
def reset_db():
    db_module._reset_pool()
    yield
    db_module._reset_pool()


def test_resolve_secrets_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/test")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",)]
    mock_cursor.fetchall.return_value = [(1,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()
    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        rows = db_module.query("SELECT id FROM patients")
    assert rows == [{"id": 1}]


def test_resolve_secrets_from_secretsmanager(monkeypatch):
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:...:secret:db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AWS_REGION", "eu-west-2")

    secret_payload = '{"username": "u", "password": "p", "host": "db.host", "dbname": "variants", "port": 5432}'
    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": secret_payload}

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "test")]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("boto3.client", return_value=mock_sm), \
         patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        rows = db_module.query("SELECT id, name FROM patients")

    assert rows == [{"id": 1, "name": "test"}]
    assert "DATABASE_URL" in os.environ
    assert "u" in os.environ["DATABASE_URL"]


def test_resolve_secrets_missing_both_env_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL or DB_SECRET_ARN"):
        db_module._resolve_secrets()


def test_resolve_secrets_incomplete_secret(monkeypatch):
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:...:secret:db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    incomplete = '{"username": "u", "password": "p"}'  # missing host + dbname
    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": incomplete}
    with patch("boto3.client", return_value=mock_sm):
        with pytest.raises(RuntimeError, match="missing fields"):
            db_module._resolve_secrets()


def test_with_transaction_commits_on_success(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        with db_module.with_transaction() as conn:
            conn.execute("INSERT INTO x VALUES (1)")
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()


def test_with_transaction_rollbacks_on_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        with pytest.raises(ValueError):
            with db_module.with_transaction():
                raise ValueError("oops")
        mock_conn.rollback.assert_called_once()
