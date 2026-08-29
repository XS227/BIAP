from datetime import time

from kiasha_ai import KiashaAIProposal
from kiasha_paper import evaluate_ai_paper_proposal
from risk import RiskPolicy


def _policy(**overrides):
    values = dict(
        kill_switch=False,
        max_quantity=100_000,
        max_order_notional=2_000_000_000.0,
        max_daily_notional=5_000_000_000.0,
        max_symbol_position=200_000.0,
        max_limit_deviation_pct=5.0,
        min_buy_score=0.10,
        max_sell_score=-0.10,
        enforce_market_session=False,
        market_session_open=time(9, 0),
        market_session_close=time(12, 30),
    )
    values.update(overrides)
    return RiskPolicy(**values)


def _proposal(**overrides):
    values = dict(
        code="فولاد",
        horizon="short",
        action="BUY",
        confidence=0.70,
        position_pct=2.5,
        thesis="verified test proposal",
        risks=["test risk"],
        model="claude-sonnet-5",
        execution_allowed=False,
    )
    values.update(overrides)
    return KiashaAIProposal(**values)


def test_low_confidence_ai_buy_is_blocked_before_risk_or_broker():
    result = evaluate_ai_paper_proposal(
        _proposal(confidence=0.45),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(),
        min_confidence=0.55,
        execute=True,
    )
    assert result.allowed is False
    assert result.receipt is None
    assert result.risk is None
    assert any("below Paper minimum" in reason for reason in result.reasons)


def test_missing_verified_price_is_blocked():
    result = evaluate_ai_paper_proposal(
        _proposal(),
        portfolio_value=100_000_000,
        reference_price=None,
        risk_policy=_policy(),
        execute=True,
    )
    assert result.allowed is False
    assert result.receipt is None
    assert any("reference price" in reason for reason in result.reasons)


def test_deterministic_risk_can_reject_ai_buy():
    result = evaluate_ai_paper_proposal(
        _proposal(position_pct=10.0),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(max_order_notional=1_000_000),
        execute=True,
    )
    assert result.allowed is False
    assert result.receipt is None
    assert result.risk is not None
    assert result.risk["allowed"] is False
    assert any("order notional exceeds" in reason for reason in result.reasons)


def test_safe_buy_dry_run_builds_paper_intent_without_fill():
    result = evaluate_ai_paper_proposal(
        _proposal(),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(),
        min_confidence=0.55,
        execute=False,
    )
    assert result.allowed is True
    assert result.intent is not None
    assert result.intent["mode"] == "paper"
    assert result.intent["side"] == "BUY"
    assert result.receipt is None
    assert result.to_dict()["paperExecution"] is False
    assert result.to_dict()["liveExecution"] is False


def test_position_pct_is_capped_by_deterministic_limit():
    result = evaluate_ai_paper_proposal(
        _proposal(position_pct=20.0),
        portfolio_value=100_000_000,
        reference_price=10_000,
        risk_policy=_policy(),
        max_position_pct=5.0,
        execute=False,
    )
    assert result.allowed is True
    assert result.intent is not None
    assert result.intent["quantity"] == 500  # 5,000,000 / 10,000


def test_safe_buy_execute_reaches_paper_broker_only():
    result = evaluate_ai_paper_proposal(
        _proposal(),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(),
        min_confidence=0.55,
        execute=True,
    )
    assert result.allowed is True
    assert result.receipt is not None
    assert result.receipt["status"] == "PAPER_FILLED"
    assert result.receipt["broker"] == "paper"
    assert result.receipt["brokerOrderId"].startswith("paper-")
    assert result.to_dict()["liveExecution"] is False


def test_hold_or_ai_execution_flag_is_blocked():
    hold = evaluate_ai_paper_proposal(
        _proposal(action="HOLD", position_pct=0.0),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(),
        execute=True,
    )
    assert hold.allowed is False
    assert hold.receipt is None

    unsafe = evaluate_ai_paper_proposal(
        _proposal(execution_allowed=True),
        portfolio_value=100_000_000,
        reference_price=2698,
        risk_policy=_policy(),
        execute=True,
    )
    assert unsafe.allowed is False
    assert unsafe.receipt is None
    assert any("executionAllowed=false" in reason for reason in unsafe.reasons)
