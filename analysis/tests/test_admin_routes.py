import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import admin_routes
import api_server as m
from admin_store import AdminStore
from audit_store import AuditStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_ADMIN_JWT_SECRET", "test-admin-secret")
    m.AUDIT = AuditStore(db_path=str(tmp_path / "audit.sqlite3"))
    admin_routes._AUDIT = m.AUDIT
    admin_routes._ADMIN_STORE = AdminStore(db_path=str(tmp_path / "admin.sqlite3"))
    admin_routes._ADMIN_STORE.create_operator("khabat", "s3cret-pass")
    # base_url must be https: the admin session cookie is Secure (this panel
    # sits behind nginx TLS termination in production), so an http test
    # client would silently never send it back on subsequent requests.
    return TestClient(m.app, base_url="https://testserver")


def _login(client, username="khabat", password="s3cret-pass"):
    return client.post(
        "/admin/login", data={"username": username, "password": password}, follow_redirects=False
    )


def _approval_intent(client, user_headers, quantity=10):
    preview = client.post(
        "/orders/preview",
        json={"code": "SAMPLE1", "side": "BUY", "quantity": quantity, "mode": "approval"},
        headers=user_headers,
    )
    intent_id = preview.json()["intent"]["id"]
    client.post("/orders/submit", json={"intentId": intent_id}, headers=user_headers)
    return intent_id


def test_dashboard_redirects_when_not_logged_in(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login"


def test_login_wrong_password_does_not_authenticate(client):
    r = _login(client, password="wrong")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/login")
    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code == 303


def test_login_then_dashboard_accessible(client):
    r = _login(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "khabat" in r2.text


def test_admin_can_approve_pending_order_and_audit_records_actor(client):
    user_headers = {"Authorization": "Bearer some-user-token"}
    intent_id = _approval_intent(client, user_headers)

    order = client.get(f"/orders/{intent_id}", headers=user_headers).json()
    assert order["status"] == "PENDING_APPROVAL"

    _login(client)
    r = client.post(f"/admin/orders/{intent_id}/approve", follow_redirects=False)
    assert r.status_code == 303

    order_after = client.get(f"/orders/{intent_id}", headers=user_headers).json()
    assert order_after["status"] == "APPROVED"

    events = m.AUDIT.list_all_events(limit=50)
    approved_events = [e for e in events if e["eventType"] == "ORDER_APPROVED"]
    assert approved_events, "expected an ORDER_APPROVED audit event"
    assert approved_events[0]["payload"]["actor"] == "admin:khabat"


def test_admin_orders_and_audit_pages_require_login(client):
    assert client.get("/admin/orders", follow_redirects=False).status_code == 303
    assert client.get("/admin/audit", follow_redirects=False).status_code == 303


def test_login_page_503_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("BIAP_ADMIN_JWT_SECRET", raising=False)
    r = client.get("/admin/login")
    assert r.status_code == 503
