from audit_store import AuditStore
from execution import ExecutionMode, build_order_intent, submit_order_intent
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore


def _proposal(action: str):
    return {
        "code": "فولاد",
        "horizon": "short",
        "action": action,
        "confidence": 0.70,
        "positionPct": 2.5,
        "thesis": "test-only verified-data thesis",
        "risks": ["test risk"],
        "model": "test-model",
        "executionAllowed": False,
    }


def _risk():
    return {"allowed": True, "reasons": [], "checks": {"marketSessionOpen": True}}


def _intent(side: str, quantity: int, price: float):
    return build_order_intent(
        code="فولاد",
        side=side,
        quantity=quantity,
        limit_price=price,
        mode=ExecutionMode.PAPER.value,
        recommendation_call=side,
        recommendation_score=0.70 if side == "BUY" else -0.70,
    )


def test_paper_buy_partial_sell_full_sell_roundtrip(tmp_path):
    db = str(tmp_path / "audit.sqlite3")
    audit = AuditStore(db)
    buys = PaperExecutionStore(db)
    sells = PaperSellStore(db)
    audit.ensure_paper_account(user_id="roundtrip-user", initial_cash=1_000_000)

    buy = _intent("BUY", 100, 2_500)
    buys.commit_buy_fill(
        user_id="roundtrip-user", code="فولاد", horizon="short",
        proposal=_proposal("BUY"), risk=_risk(), intent=buy,
        receipt=submit_order_intent(buy), reference_price=2_500,
        reference_source="verified-market-quote", idempotency_key="roundtrip-buy-1",
    )
    account = audit.get_paper_account(user_id="roundtrip-user")
    assert account["cashBalance"] == 750_000.0
    assert account["positions"][0]["quantity"] == 100
    assert account["positions"][0]["avgCost"] == 2_500.0

    sell1 = _intent("SELL", 40, 3_000)
    r1 = sells.commit_sell_fill(
        user_id="roundtrip-user", code="فولاد", horizon="short",
        proposal=_proposal("SELL"), risk=_risk(), intent=sell1,
        receipt=submit_order_intent(sell1), reference_price=3_000,
        reference_source="verified-market-quote", idempotency_key="roundtrip-sell-1",
    )
    account = audit.get_paper_account(user_id="roundtrip-user")
    assert account["cashBalance"] == 870_000.0
    assert account["positions"][0]["quantity"] == 60
    assert account["positions"][0]["avgCost"] == 2_500.0
    assert r1["realizedPnL"] == 20_000.0
    assert r1["liveExecution"] is False

    sell2 = _intent("SELL", 60, 2_000)
    r2 = sells.commit_sell_fill(
        user_id="roundtrip-user", code="فولاد", horizon="short",
        proposal=_proposal("SELL"), risk=_risk(), intent=sell2,
        receipt=submit_order_intent(sell2), reference_price=2_000,
        reference_source="verified-market-quote", idempotency_key="roundtrip-sell-2",
    )
    account = audit.get_paper_account(user_id="roundtrip-user")
    assert account["cashBalance"] == 990_000.0
    assert account["positions"] == []
    assert r2["realizedPnL"] == -30_000.0
    assert r2["paperExecution"] is True
    assert r2["liveExecution"] is False

    event_types = [e["eventType"] for e in audit.list_events(user_id="roundtrip-user")]
    assert "KIASHA_AI_PAPER_FILLED" in event_types
    assert event_types.count("KIASHA_AI_PAPER_SOLD") == 2
