from datetime import datetime, timedelta, timezone

from agents import AgentVote
import kiasha
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore


def _breakdown(vote=0.4, agent="fundamental"):
    return [{"agent": agent, "vote": vote, "confidence": 0.7}]


def _record(store, when, *, vote=0.4, price=100.0, symbol="فولاد"):
    return store.record_recommendation(
        code="46348559193224090",
        symbol=symbol,
        generated_at=when.isoformat(),
        reference_price=price,
        kiasha_call="BUY",
        weighted_score=0.3,
        breakdown=_breakdown(vote=vote),
        horizon_trading_days=5,
    )


def test_duplicate_recommendation_does_not_double_count(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    first = _record(store, when)
    second = _record(store, when + timedelta(hours=3))

    assert first == second
    assert len(store.pending_observations()) == 1


def test_missing_future_price_stays_unevaluated(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation_id = _record(store, when)

    assert store.evaluate_observation(
        observation_id,
        future_price=None,
        observed_at=(when + timedelta(days=10)).isoformat(),
        trading_days_elapsed=5,
    ) is False
    assert len(store.pending_observations()) == 1
    assert store.agent_stats("fundamental") is None


def test_pre_recommendation_price_cannot_evaluate_future(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 10, tzinfo=timezone.utc)
    observation_id = _record(store, when)

    assert store.evaluate_observation(
        observation_id,
        future_price=110.0,
        observed_at=(when - timedelta(minutes=1)).isoformat(),
        trading_days_elapsed=5,
    ) is False
    assert store.agent_stats("fundamental") is None


def test_horizon_must_be_reached_before_evaluation(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation_id = _record(store, when)

    assert store.evaluate_observation(
        observation_id,
        future_price=110.0,
        observed_at=(when + timedelta(days=7)).isoformat(),
        trading_days_elapsed=4,
    ) is False
    assert store.agent_stats("fundamental") is None


def test_neutral_vote_is_excluded_from_accuracy_denominator(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation_id = _record(store, when, vote=0.0)

    assert store.evaluate_observation(
        observation_id,
        future_price=120.0,
        observed_at=(when + timedelta(days=10)).isoformat(),
        trading_days_elapsed=5,
    ) is True
    assert store.agent_stats("fundamental") is None


def test_no_real_history_uses_fallback_track_record(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)

    record, source, samples = kiasha._track_record_for_agent("fundamental")

    assert source == "fallback"
    assert samples == 0
    assert record == kiasha.TRACK_RECORDS["fundamental"]


def test_insufficient_real_history_still_uses_fallback(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(MIN_OBSERVED_SAMPLES - 1):
        when = start + timedelta(days=i)
        observation_id = _record(store, when)
        assert store.evaluate_observation(
            observation_id,
            future_price=110.0,
            observed_at=(when + timedelta(days=10)).isoformat(),
            trading_days_elapsed=5,
        )
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)

    record, source, samples = kiasha._track_record_for_agent("fundamental")

    assert source == "fallback"
    assert samples == MIN_OBSERVED_SAMPLES - 1
    assert record == kiasha.TRACK_RECORDS["fundamental"]


def test_sufficient_real_history_switches_to_observed_trust(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(MIN_OBSERVED_SAMPLES):
        when = start + timedelta(days=i)
        observation_id = _record(store, when)
        future_price = 110.0 if i < 40 else 90.0
        assert store.evaluate_observation(
            observation_id,
            future_price=future_price,
            observed_at=(when + timedelta(days=10)).isoformat(),
            trading_days_elapsed=5,
        )
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)

    record, source, samples = kiasha._track_record_for_agent("fundamental")

    assert source == "observed"
    assert samples == MIN_OBSERVED_SAMPLES
    assert record.lifetime_calls == MIN_OBSERVED_SAMPLES
    assert record.accuracy == 0.8


def test_decision_breakdown_labels_fallback_trust_without_changing_call_logic(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    monkeypatch.setattr(
        kiasha,
        "run_team",
        lambda _company: [
            AgentVote("fundamental", 0.4, 0.75, "test"),
            AgentVote("risk", -0.2, 0.6, "test"),
            AgentVote("forecast", 0.2, 0.5, "test"),
            AgentVote("comparison", 1.0, 0.65, "test"),
        ],
    )
    company = {"ticker": "TEST", "name_fa": "تست", "market": {"price": None}}

    decision = kiasha.decide(company)

    assert decision.call in {"BUY", "HOLD", "SELL"}
    assert all(item["trust_source"] == "fallback" for item in decision.breakdown)
    assert all(item["observed_samples"] == 0 for item in decision.breakdown)
