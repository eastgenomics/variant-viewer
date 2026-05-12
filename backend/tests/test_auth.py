"""Tests for API key authentication middleware and db.run_in_transaction helper."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.middleware.auth as auth_module


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key-123")
    with TestClient(app) as c:
        yield c


def test_health_no_auth_required(client):
    r = client.get("/api/health")
    assert r.status_code == 200


def test_protected_route_no_key_returns_401(monkeypatch):
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        monkeypatch.setenv("API_KEY", "secret-key-123")
        monkeypatch.setattr(auth_module, "_resolved_key", None)
        r = tc.get("/ping")
        assert r.status_code == 401


def test_protected_route_wrong_key_returns_401(monkeypatch):
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        monkeypatch.setenv("API_KEY", "secret-key-123")
        monkeypatch.setattr(auth_module, "_resolved_key", None)
        r = tc.get("/ping", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401


def test_protected_route_correct_key_passes(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key-123")
    monkeypatch.setattr(auth_module, "_resolved_key", None)
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        r = tc.get("/ping", headers={"X-API-Key": "secret-key-123"})
        assert r.status_code == 200


def test_auth_resolves_from_secrets_manager(monkeypatch):
    import json
    from unittest.mock import MagicMock, patch
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:...:secret:api-key")
    monkeypatch.setattr(auth_module, "_resolved_key", None)

    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {
        "SecretString": json.dumps({"api_key": "sm-resolved-key"})
    }
    with patch("boto3.client", return_value=mock_sm):
        key = auth_module._get_api_key()
    assert key == "sm-resolved-key"


def test_auth_raises_if_neither_env_set(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_SECRET_ARN", raising=False)
    monkeypatch.setattr(auth_module, "_resolved_key", None)
    with pytest.raises(RuntimeError, match="API_KEY or API_KEY_SECRET_ARN"):
        auth_module._get_api_key()


def test_auth_raises_if_secret_missing_api_key_field(monkeypatch):
    """Secrets Manager secret exists but was created with wrong key name."""
    import json
    from unittest.mock import MagicMock, patch
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:...:secret:api-key")
    monkeypatch.setattr(auth_module, "_resolved_key", None)

    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {
        "SecretString": json.dumps({"API_KEY": "wrong-field-name"})
    }
    with patch("boto3.client", return_value=mock_sm):
        with pytest.raises(RuntimeError, match="must contain an 'api_key' field"):
            auth_module._get_api_key()


def test_run_in_transaction_commits(monkeypatch):
    import app.lib.db as db_module
    from unittest.mock import MagicMock, patch
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    db_module._reset_pool()

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        result = db_module.run_in_transaction(lambda conn: "done")
    assert result == "done"
    mock_conn.commit.assert_called_once()
