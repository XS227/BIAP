import pytest

from audit_store import AuditStore
from execution import ExecutionMode, build_order_intent, submit_order_intent
from paper_execution_store import PaperExecutionStore


def _proposal():
    return {
        "code": "فولاد",
        "horizon": "short",
        "action": "BUY",
        "confidence": 0.70,
        "positionPct": 2.5,
        "thesis": "verified-data thesis",
        "risks": ["test risk"],
        "model": "test-model",
        "executionAllowed": False,
    }


def _risk():
    return {"allowed": True, "reasons": [], "checks": {"marketSessionOpen": True}}


def _intent_and_receipt():
    intent = build_order_intent(
        code="فولاد",
        side="BUY",
        quantity=100,
        limit_price=2_500,
        mode=ExecutionMode.PAPER.value,
        recommendation_call="BUY",
        recommendation_score=0.70,
    )
    return intent, submit_order_intent(intent)


def _commit(executor, *, user_id, key):
    intent, receipt = _intent_and_receipt()
    return executor.commit_buy_fill(
        user_id=user_id,
        code="فولاد",
        horizon="short",
        proposal=_proposal(),
        risk=_risk(),
        intent=intent,
        receipt=receipt,
        reference_price=2_500,
        reference_source="verified-market-quote",
        idempotency_key=key,
    )


def test_atomic_paper_simulation_updates_ledger_and_audit(tmp_path):
    db_path = str(tmp_path / "audit.sqlite3")
    audit = AuditStore(db_path)
    executor = PaperExecutionStore(db_path)
    audit.ensure_paper_account(user_id="user-a", initial_cash=100_000_000)
    intent, receipt = _intent_and_receipt()

    result = executor.commit_buy_fill(
        user_id="user-a",
        code="فولاد",
        horizon="short",
        proposal=_proposal(),
        risk=_risk(),
        intent=intent,
        receipt=receipt,
        reference_price=2_500,
        reference_source="verified-market-quote",
        idempotency_key="paper-test-0001",
    )

    account = audit.get_paper_account(user_id="user-a")
    assert account is not None
    assert account["cashBalance"] == 99_750_000.0
    assert account["positions"][0]["quantity"] == 100
    assert account["positions"][0]["avgCost"] == 2_500.0
    assert result["paperExecution"] is True
    assert result["liveExecution"] is False
    assert result["dailyNotionalBefore"] == 0.0
    assert result["dailyNotionalAfter"] == 250_000.0
    assert audit.get_intent(intent["id"], user_id="user-a")["status"] == "PAPER_FILLED"
    assert audit.list_events(user_id="user-a")[0]["eventType"] == "KIASHA_AI_PAPER_FILLED"


def test_same_simulation_idempotency_key_is_applied_once(tmp_path):
    db_path = str(tmp_path / "audit.sqlite3")
    audit = AuditStore(db_path)
    executor = PaperExecutionStore(db_path)
    audit.ensure_paper_account(user_id="user-a", initial_cash=1_000_000)
    intent, receipt = _intent_and_receipt()
    kwargs = dict(
        user_id="user-a",
        code="فولاد",
        horizon="short",
        proposal=_proposal(),
        risk=_risk(),
        intent=intent,
        receipt=receipt,
        reference_price=2_500,
        reference_source="verified-market-quote",
        idempotency_key="paper-test-0002",
    )

    first = executor.commit_buy_fill(**kwargs)
    second = executor.commit_buy_fill(**kwargs)
    account = audit.get_paper_account(user_id="user-a")

    assert account is not None
    assert first == second
    assert account["cashBalance"] == 750_000.0
    assert account["positions"][0]["quantity"] == 100
    assert len(audit.list_kiasha_ai_decisions(user_id="user-a")) == 1


def test_daily_paper_notional_is_enforced_per_user_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_MAX_DAILY_NOTIONAL", "400000")
    db_path = str(tmp_path / "audit.sqlite3")
    audit = AuditStore(db_path)
    executor = PaperExecutionStore(db_path)
    audit.ensure_paper_account(user_id="user-a", initial_cash=1_000_000)
    audit.ensure_paper_account(user_id="user-b", initial_cash=1_000_000)

    first = _commit(executor, user_id="user-a", key="daily-user-a-1")
    assert first["dailyNotionalAfter"] == 250_000.0

    with pytest.raises(ValueError, match="projected user Paper daily notional exceeds max 400000"):
        _commit(executor, user_id="user-a", key="daily-user-a-2")

    account_a = audit.get_paper_account(user_id="user-a")
    assert account_a is not None
    assert account_a["cashBalance"] == 750_000.0
    assert account_a["positions"][0]["quantity"] == 100

    other_user = _commit(executor, user_id="user-b", key="daily-user-b-1")
    assert other_user["paperExecution"] is True
    assert other_user["dailyNotionalBefore"] == 0.0
    assert other_user["dailyNotionalAfter"] == 250_000.0
