import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import api_server as m
from audit_store import AuditStore
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "audit.sqlite3")
    m.AUDIT = AuditStore(db_path=db)
    m.PAPER_BUY_STORE = PaperExecutionStore(db)
    m.PAPER_SELL_STORE = PaperSellStore(db)
    return TestClient(m.app)


def _user_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def _preview(client, headers, quantity=10, idempotency_key=None, side="BUY"):
    h = dict(headers)
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return client.post(
        "/orders/preview",
        json={"code": "SAMPLE1", "side": side, "quantity": quantity, "mode": "paper"},
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
    account_after_first = m.AUDIT.get_paper_account(user_id=_user_id("token-a"))
    second = client.post("/orders/submit", json={"intentId": intent_id}, headers=headers).json()
    account_after_second = m.AUDIT.get_paper_account(user_id=_user_id("token-a"))

    assert first["status"] == "PAPER_FILLED"
    assert second["submittedAt"] == first["submittedAt"]
    assert account_after_first == account_after_second
    assert account_after_first is not None
    assert account_after_first["positions"][0]["quantity"] == 10


def test_generic_paper_buy_and_sell_update_ledger_exactly_once(client, monkeypatch):
    headers = {"Authorization": "Bearer ledger-user"}
    user_id = _user_id("ledger-user")

    monkeypatch.setattr(m, "decide", lambda _company: SimpleNamespace(call="BUY", weighted_score=0.70, breakdown=[]))
    buy_preview = _preview(client, headers, quantity=10, side="BUY")
    assert buy_preview.status_code == 200
    buy_intent = buy_preview.json()["intent"]
    buy_price = float(buy_intent["referencePrice"])

    first_buy = client.post("/orders/submit", json={"intentId": buy_intent["id"]}, headers=headers)
    assert first_buy.status_code == 200
    assert first_buy.json()["status"] == "PAPER_FILLED"
    after_buy = m.AUDIT.get_paper_account(user_id=user_id)
    assert after_buy is not None
    assert after_buy["positions"][0]["quantity"] == 10
    assert after_buy["cashBalance"] == pytest.approx(m.DEFAULT_PAPER_INITIAL_CASH - 10 * buy_price)

    retry_buy = client.post("/orders/submit", json={"intentId": buy_intent["id"]}, headers=headers)
    assert retry_buy.status_code == 200
    assert m.AUDIT.get_paper_account(user_id=user_id) == after_buy

    monkeypatch.setattr(m, "decide", lambda _company: SimpleNamespace(call="SELL", weighted_score=-0.70, breakdown=[]))
    sell_preview = _preview(client, headers, quantity=4, side="SELL")
    assert sell_preview.status_code == 200
    sell_intent = sell_preview.json()["intent"]
    sell_price = float(sell_intent["referencePrice"])

    first_sell = client.post("/orders/submit", json={"intentId": sell_intent["id"]}, headers=headers)
    assert first_sell.status_code == 200
    assert first_sell.json()["status"] == "PAPER_FILLED"
    after_sell = m.AUDIT.get_paper_account(user_id=user_id)
    assert after_sell is not None
    assert after_sell["positions"][0]["quantity"] == 6
    assert after_sell["cashBalance"] == pytest.approx(after_buy["cashBalance"] + 4 * sell_price)

    retry_sell = client.post("/orders/submit", json={"intentId": sell_intent["id"]}, headers=headers)
    assert retry_sell.status_code == 200
    assert m.AUDIT.get_paper_account(user_id=user_id) == after_sell
