import pytest

from execution import ExecutionMode, ExecutionPolicyError, submit_order_intent, validate_intent


def test_auto_execution_is_always_rejected_by_policy():
    with pytest.raises(ExecutionPolicyError, match="AUTO execution is disabled"):
        validate_intent(
            code="فولاد", side="BUY", quantity=10, mode=ExecutionMode.AUTO.value,
            recommendation_call="BUY", recommendation_score=0.5,
        )


def test_submit_order_intent_rejects_auto_mode_even_if_flagged_live(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    intent = {
        "id": "test-auto-intent", "code": "فولاد", "side": "BUY", "quantity": 10,
        "limit_price": 1000.0, "mode": ExecutionMode.AUTO.value, "status": "PENDING",
        "recommendation_call": "BUY", "recommendation_score": 0.5,
        "created_at": "2026-01-01T00:00:00+00:00", "note": "test",
    }
    with pytest.raises(ExecutionPolicyError, match="AUTO execution is disabled"):
        submit_order_intent(intent)


def test_paper_mode_fill_never_reports_live_execution():
    intent = {
        "id": "test-paper-intent", "code": "فولاد", "side": "BUY", "quantity": 10,
        "limit_price": 1000.0, "mode": ExecutionMode.PAPER.value, "status": "SIMULATED",
        "recommendation_call": "BUY", "recommendation_score": 0.5,
        "created_at": "2026-01-01T00:00:00+00:00", "note": "test",
    }
    receipt = submit_order_intent(intent)
    assert receipt["status"] == "PAPER_FILLED"
    assert receipt["broker"] == "paper"
