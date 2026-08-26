import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import api_server as m
from audit_store import AuditStore


@pytest.fixture
def client(tmp_path):
    m.AUDIT = AuditStore(db_path=str(tmp_path / "audit.sqlite3"))
    return TestClient(m.app)


def _preview(client, headers, quantity=10, idempotency_key=None):
    h = dict(headers)
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return client.post(
        "/orders/preview",
        json={"code": "SAMPLE1", "side": "BUY", "quantity": quantity, "mode": "paper"},
        headers=h,
    )


def test_orders_require_bearer_token(client):
    r = _preview(client, headers={})
    assert r.status_code == 401


def test_users_cannot_see_each_others_orders(client):
    user_a = {"Authorization": "Bearer token-a"}
    user_b = {"Authorization": "Bearer token-b"}

    intent_id = _preview(client, user_a).json()["intent"]["id"]

    assert client.get(f"/orders/{intent_id}", headers=user_b).status_code == 404
    assert client.get(f"/orders/{intent_id}", headers=user_a).status_code == 200

    assert client.get("/audit/orders", headers=user_b).json()["items"] == []
    assert len(client.get("/audit/orders", headers=user_a).json()["items"]) == 1


def test_repeated_idempotency_key_returns_same_intent_without_duplicating(client):
    headers = {"Authorization": "Bearer token-c"}

    first = _preview(client, headers, idempotency_key="retry-1").json()
    second = _preview(client, headers, idempotency_key="retry-1").json()

    assert first["intent"]["id"] == second["intent"]["id"]
    assert len(client.get("/audit/orders", headers=headers).json()["items"]) == 1


def test_different_users_can_reuse_the_same_idempotency_key(client):
    user_a = {"Authorization": "Bearer token-a"}
    user_b = {"Authorization": "Bearer token-b"}

    first = _preview(client, user_a, idempotency_key="shared-key").json()
    second = _preview(client, user_b, idempotency_key="shared-key").json()

    assert first["intent"]["id"] != second["intent"]["id"]


def test_double_submit_is_a_no_op_not_a_second_fill(client):
    headers = {"Authorization": "Bearer token-a"}
    intent_id = _preview(client, headers).json()["intent"]["id"]

    first = client.post("/orders/submit", json={"intentId": intent_id}, headers=headers).json()
    second = client.post("/orders/submit", json={"intentId": intent_id}, headers=headers).json()

    assert first["status"] == "PAPER_FILLED"
    assert second["submittedAt"] == first["submittedAt"]
