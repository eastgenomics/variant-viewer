"""Tests for PR 7 classification routes: score-only, persist, reset."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import app.middleware.auth as auth_module

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.main import app
    with TestClient(app) as c:
        yield c


_ACGS_CRITERIA_PAYLOAD = {
    "criteria": [
        {"criterion_code": "PVS1", "applied": True, "strength": "very_strong"},
        {"criterion_code": "PM2",  "applied": True, "strength": "supporting"},
    ],
    "framework": "acgs_snv",
    "combination_rules": [],
    "locked_by": "analyst-1",
    "user_id": "analyst-1",
}


def test_classify_score_only_no_persist(client, monkeypatch):
    """POST /classify returns score without writing to DB."""
    call_log: list[str] = []
    monkeypatch.setattr("app.lib.db.run_in_transaction",
        lambda fn: call_log.append("CALLED") or None)

    r = client.post("/api/variants/100/classify",
                    json={k: v for k, v in _ACGS_CRITERIA_PAYLOAD.items()
                          if k in ("criteria", "framework", "combination_rules")},
                    headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 9
    assert body["classification"] == "Likely_Pathogenic"
    assert call_log == []   # no DB write


def test_classify_persist_locks_classification(client, monkeypatch):
    """PUT /classification persists and locks the record."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 100, "case_type": "germline", "gene": "BRCA1"}
    ] if "FROM variants" in sql else [])

    calls: list[tuple] = []  # (sql, params) pairs

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (99,)  # new classification_id
        mock_cursor.execute.side_effect = lambda sql, p=(): calls.append((sql, p))
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.put("/api/variants/100/classification",
                   json=_ACGS_CRITERIA_PAYLOAD, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 9
    assert body["classification"] == "Likely_Pathogenic"

    sqls = [s for s, _ in calls]
    assert any("INSERT INTO variant_classification" in s for s in sqls)
    assert any("INSERT INTO classification_criterion" in s for s in sqls)
    assert any("INSERT INTO audit_log" in s for s in sqls)

    # Assert the classification INSERT carries the correct variant_id, framework, locked_by
    cls_params = next(
        (p for s, p in calls if "INSERT INTO variant_classification" in s and "locked_by" in s),
        None,
    )
    assert cls_params is not None, "Classification INSERT not found"
    assert cls_params[0] == 100          # variant_id
    assert cls_params[1] == "acgs_snv"   # framework
    assert cls_params[5] == "analyst-1"  # locked_by


def test_classify_persist_soft_deletes_existing(client, monkeypatch):
    """PUT /classification soft-deletes any existing active classification first."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 100, "case_type": "germline", "gene": "BRCA1"}
    ] if "FROM variants" in sql else [])

    calls: list[tuple] = []  # (sql, params) pairs

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mc = MagicMock()
        mc.__enter__ = lambda s: s
        mc.__exit__ = MagicMock(return_value=False)
        mc.fetchone.return_value = (99,)
        mc.execute.side_effect = lambda sql, p=(): calls.append((sql, p))
        mock_conn.cursor.return_value = mc
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    client.put("/api/variants/100/classification",
               json=_ACGS_CRITERIA_PAYLOAD, headers=HEADERS)

    # Soft-delete UPDATE must target the correct variant_id
    soft_delete = next(
        ((s, p) for s, p in calls if "deleted_at" in s and "UPDATE" in s),
        None,
    )
    assert soft_delete is not None, "Soft-delete UPDATE not found"
    assert soft_delete[1][0] == 100, "Soft-delete WHERE must use variant_id=100"


def test_classify_reset_soft_deletes_and_creates_blank(client, monkeypatch):
    """DELETE /classification/{id} soft-deletes and inserts a blank replacement."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 50, "variant_id": 100, "framework": "acgs_snv",
         "framework_version": "ACGS 2024"}
    ] if params == (50, 100) else [])

    calls: list[tuple] = []  # (sql, params) pairs

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mc = MagicMock()
        mc.__enter__ = lambda s: s
        mc.__exit__ = MagicMock(return_value=False)
        mc.fetchone.return_value = (51,)
        mc.rowcount = 1
        mc.execute.side_effect = lambda sql, p=(): calls.append((sql, p))
        mock_conn.cursor.return_value = mc
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.request("DELETE", "/api/variants/100/classification/50",
                        json={"user_id": "analyst-1"}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["new_classification_id"] == 51

    sqls = [s for s, _ in calls]
    assert any("deleted_at" in s for s in sqls)
    assert any("INSERT INTO variant_classification" in s for s in sqls)
    assert any("INSERT INTO audit_log" in s for s in sqls)

    # Soft-delete targets the correct classification_id
    soft_delete_params = next(
        (p for s, p in calls if "deleted_at" in s and "UPDATE" in s), None
    )
    assert soft_delete_params is not None, "Soft-delete UPDATE not found"
    assert soft_delete_params[0] == 50  # classification_id

    # Blank replacement INSERT carries the correct variant_id
    blank_params = next(
        (p for s, p in calls if "INSERT INTO variant_classification" in s), None
    )
    assert blank_params is not None, "Blank INSERT not found"
    assert blank_params[0] == 100  # variant_id


def test_classify_reset_concurrent_modification_returns_409(client, monkeypatch):
    """If the classification row is deleted between SELECT and UPDATE, return 409."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 50, "variant_id": 100, "framework": "acgs_snv",
         "framework_version": "ACGS 2024"}
    ] if params == (50, 100) else [])

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mc = MagicMock()
        mc.__enter__ = lambda s: s
        mc.__exit__ = MagicMock(return_value=False)
        mc.rowcount = 0  # simulate concurrent deletion
        mock_conn.cursor.return_value = mc
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.request("DELETE", "/api/variants/100/classification/50",
                        json={"user_id": "analyst-1"}, headers=HEADERS)
    assert r.status_code == 409
    assert "Concurrent" in r.json()["detail"]


def test_classify_reset_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.request("DELETE", "/api/variants/100/classification/999",
                        json={"user_id": "analyst-1"}, headers=HEADERS)
    assert r.status_code == 404


def test_classify_unknown_framework_returns_422(client, monkeypatch):
    """Sending an unknown framework value must return 422 from Pydantic validation."""
    r = client.post("/api/variants/100/classify",
                    json={"criteria": [], "framework": "unknown_framework",
                          "combination_rules": []},
                    headers=HEADERS)
    assert r.status_code == 422
