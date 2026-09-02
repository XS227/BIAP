from dataclasses import replace
from datetime import datetime, time, timezone

from risk import evaluate_order_risk, load_policy


def _base_policy(**overrides):
    policy = replace(
        load_policy(),
        enforce_market_session=True,
        market_session_open=time(9, 0),
        market_session_close=time(12, 30),
        max_symbol_position=1000,
    )
    return replace(policy, **overrides) if overrides else policy


def _common_kwargs():
    return dict(
        side="BUY",
        quantity=10,
        limit_price=None,
        reference_price=100.0,
        recommendation_score=0.5,
        daily_notional_used=0.0,
    )


# Saturday 2026-08-29 10:00 Asia/Tehran (UTC+3:30) == 06:30 UTC.
_TSE_SATURDAY_MID_SESSION_UTC = datetime(2026, 8, 29, 6, 30, tzinfo=timezone.utc)
# Thursday 2026-08-27 10:00 Asia/Tehran -- TSE's weekend.
_TSE_THURSDAY_UTC = datetime(2026, 8, 27, 6, 30, tzinfo=timezone.utc)
# Saturday 2026-08-29 07:00 Asia/Tehran -- before the 09:00 open.
_TSE_SATURDAY_BEFORE_OPEN_UTC = datetime(2026, 8, 29, 3, 30, tzinfo=timezone.utc)
# Saturday 2026-08-29 14:00 Asia/Tehran -- after the 12:30 close.
_TSE_SATURDAY_AFTER_CLOSE_UTC = datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc)


def test_allows_order_during_ordinary_trading_session():
    decision = evaluate_order_risk(
        **_common_kwargs(), policy=_base_policy(), now=_TSE_SATURDAY_MID_SESSION_UTC
    )
    assert decision.checks["marketSessionOpen"] is True
    assert decision.allowed is True


def test_rejects_order_on_tse_weekend():
    decision = evaluate_order_risk(
        **_common_kwargs(), policy=_base_policy(), now=_TSE_THURSDAY_UTC
    )
    assert decision.checks["marketSessionOpen"] is False
    assert decision.allowed is False
    assert any("closed" in reason for reason in decision.reasons)


def test_rejects_order_before_session_open():
    decision = evaluate_order_risk(
        **_common_kwargs(), policy=_base_policy(), now=_TSE_SATURDAY_BEFORE_OPEN_UTC
    )
    assert decision.checks["marketSessionOpen"] is False
    assert decision.allowed is False


def test_rejects_order_after_session_close():
    decision = evaluate_order_risk(
        **_common_kwargs(), policy=_base_policy(), now=_TSE_SATURDAY_AFTER_CLOSE_UTC
    )
    assert decision.checks["marketSessionOpen"] is False
    assert decision.allowed is False


def test_market_session_check_can_be_disabled():
    decision = evaluate_order_risk(
        **_common_kwargs(),
        policy=_base_policy(enforce_market_session=False),
        now=_TSE_THURSDAY_UTC,
    )
    assert "marketSessionOpen" not in decision.checks
    assert decision.allowed is True


def test_allows_position_within_limit():
    decision = evaluate_order_risk(
        **{**_common_kwargs(), "quantity": 100},
        current_symbol_position=500,
        policy=_base_policy(),
        now=_TSE_SATURDAY_MID_SESSION_UTC,
    )
    assert decision.checks["symbolPositionWithinLimit"] is True
    assert decision.allowed is True


def test_rejects_buy_that_would_exceed_symbol_position_limit():
    decision = evaluate_order_risk(
        **{**_common_kwargs(), "quantity": 600},
        current_symbol_position=500,
        policy=_base_policy(),
        now=_TSE_SATURDAY_MID_SESSION_UTC,
    )
    assert decision.checks["symbolPositionWithinLimit"] is False
    assert decision.allowed is False
    assert any("position" in reason for reason in decision.reasons)


def test_sell_reduces_projected_position_and_can_offset_a_large_existing_long():
    decision = evaluate_order_risk(
        **{**_common_kwargs(), "side": "SELL", "quantity": 400, "recommendation_score": -0.5},
        current_symbol_position=900,
        policy=_base_policy(),
        now=_TSE_SATURDAY_MID_SESSION_UTC,
    )
    # 900 - 400 = 500, well within the 1000 cap, even though the existing
    # position alone (900) is already close to it.
    assert decision.checks["symbolPositionWithinLimit"] is True


def test_short_side_can_also_breach_the_symmetric_position_cap():
    decision = evaluate_order_risk(
        **{**_common_kwargs(), "side": "SELL", "quantity": 600, "recommendation_score": -0.5},
        current_symbol_position=-500,
        policy=_base_policy(),
        now=_TSE_SATURDAY_MID_SESSION_UTC,
    )
    assert decision.checks["symbolPositionWithinLimit"] is False
    assert decision.allowed is False


def test_missing_quote_timestamp_does_not_fabricate_staleness():
    # No quote_fetched_at at all (e.g. a CODAL-only/IPO company with no live
    # quote) must not be treated as stale -- BIAP has no real signal there.
    decision = evaluate_order_risk(
        **_common_kwargs(), policy=_base_policy(), now=_TSE_SATURDAY_MID_SESSION_UTC
    )
    assert decision.checks["quoteFreshnessOk"] is True
    assert decision.allowed is True


def test_allows_order_with_fresh_quote():
    now = _TSE_SATURDAY_MID_SESSION_UTC
    decision = evaluate_order_risk(
        **_common_kwargs(),
        quote_fetched_at=now.timestamp() - 10.0,
        policy=_base_policy(max_quote_age_seconds=60.0),
        now=now,
    )
    assert decision.checks["quoteFreshnessOk"] is True
    assert decision.allowed is True


def test_rejects_order_with_stale_quote():
    now = _TSE_SATURDAY_MID_SESSION_UTC
    decision = evaluate_order_risk(
        **_common_kwargs(),
        quote_fetched_at=now.timestamp() - 90.0,
        policy=_base_policy(max_quote_age_seconds=60.0),
        now=now,
    )
    assert decision.checks["quoteFreshnessOk"] is False
    assert decision.allowed is False
    assert any("quote is" in reason and "old" in reason for reason in decision.reasons)
