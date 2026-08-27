import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import api_server as m
from audit_store import AuditStore

TRADER = {"Authorization": "Bearer trader-token"}
APPROVER = {"Authorization": "Bearer the-real-approver-secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    m.AUDIT = AuditStore(db_path=str(tmp_path / "audit.sqlite3"))
    monkeypatch.setenv("BIAP_APPROVER_TOKEN", "the-real-approver-secret")
    return TestClient(m.app)


def _create_approval_intent(client, headers=TRADER):
    r = client.post(
        "/orders/preview",
        json={"code": "SAMPLE1", "side": "BUY", "quantity": 10, "mode": "approval"},
        headers=headers,
    )
    assert r.status_code == 200
    intent = r.json()["intent"]
    submitted = client.post("/orders/submit", json={"intentId": intent["id"]}, headers=headers)
    assert submitted.json()["status"] == "PENDING_APPROVAL"
    return intent["id"]


def test_approve_requires_configured_approver_secret(client, monkeypatch):
    monkeypatch.delenv("BIAP_APPROVER_TOKEN", raising=False)
    intent_id = _create_approval_intent(client)
    r = client.post(f"/orders/{intent_id}/approve", headers=APPROVER)
    assert r.status_code == 503


def test_approve_rejects_wrong_or_missing_token(client):
    intent_id = _create_approval_intent(client)

    r = client.post(f"/orders/{intent_id}/approve", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401

    r = client.post(f"/orders/{intent_id}/approve")
    assert r.status_code == 401


def test_a_traders_own_bearer_token_cannot_approve_their_own_order(client):
    # The whole point of a separate approver secret: the token that created
    # the order must not, by itself, also be able to approve it.
    intent_id = _create_approval_intent(client)
    r = client.post(f"/orders/{intent_id}/approve", headers=TRADER)
    assert r.status_code == 401


def test_approver_can_approve_an_order_they_did_not_create(client):
    intent_id = _create_approval_intent(client, headers=TRADER)

    r = client.post(f"/orders/{intent_id}/approve", headers=APPROVER)
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    assert "resolvedAt" in r.json()

    # The original owner still sees the resolved state via their own view.
    fetched = client.get(f"/orders/{intent_id}", headers=TRADER)
    assert fetched.json()["status"] == "APPROVED"


def test_approve_is_idempotent(client):
    intent_id = _create_approval_intent(client)
    first = client.post(f"/orders/{intent_id}/approve", headers=APPROVER).json()
    second = client.post(f"/orders/{intent_id}/approve", headers=APPROVER).json()
    assert first["status"] == second["status"] == "APPROVED"
    assert first["resolvedAt"] == second["resolvedAt"]


def test_reject_records_reason(client):
    intent_id = _create_approval_intent(client)
    r = client.post(
        f"/orders/{intent_id}/reject",
        json={"reason": "price moved too far from reference"},
        headers=APPROVER,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"
    assert r.json()["rejectionReason"] == "price moved too far from reference"


def test_reject_without_body_is_allowed(client):
    intent_id = _create_approval_intent(client)
    r = client.post(f"/orders/{intent_id}/reject", headers=APPROVER)
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"
    assert r.json()["rejectionReason"] is None


def test_cannot_approve_a_paper_mode_order(client):
    r = client.post(
        "/orders/preview",
        json={"code": "SAMPLE1", "side": "BUY", "quantity": 10, "mode": "paper"},
        headers=TRADER,
    )
    intent_id = r.json()["intent"]["id"]
    client.post("/orders/submit", json={"intentId": intent_id}, headers=TRADER)

    r = client.post(f"/orders/{intent_id}/approve", headers=APPROVER)
    assert r.status_code == 400


def test_approve_unknown_intent_is_404(client):
    r = client.post("/orders/does-not-exist/approve", headers=APPROVER)
    assert r.status_code == 404
