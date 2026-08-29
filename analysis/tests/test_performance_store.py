from datetime import datetime, timedelta, timezone

import kiasha
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore


def _breakdown(vote=1.0):
    return [{"agent": "fundamental", "vote": vote, "confidence": 0.8}]


def _record(store, *, day=1, vote=1.0, price=100.0):
    generated = datetime(2026, 1, day, 9, tzinfo=timezone.utc).isoformat()
    return store.record_recommendation(
        code="123",
        symbol="فولاد",
        generated_at=generated,
        reference_price=price,
        kiasha_call="BUY" if vote > 0 else "HOLD",
        weighted_score=0.4 if vote > 0 else 0.0,
        breakdown=_breakdown(vote),
        horizon_trading_days=5,
    )


def test_duplicate_recommendation_does_not_double_count(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    first = _record(store)
    second = _record(store)
    assert first == second
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM recommendation_observations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM agent_observations").fetchone()[0] == 1


def test_future_outcome_requires_post_recommendation_time_and_horizon(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id = _record(store)
    generated = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    assert store.evaluate_observation(observation_id,future_price=110,observed_at=(generated-timedelta(minutes=1)).isoformat(),trading_days_elapsed=5) is False
    assert store.evaluate_observation(observation_id,future_price=110,observed_at=(generated+timedelta(days=5)).isoformat(),trading_days_elapsed=4) is False
    assert store.agent_stats("fundamental") is None


def test_missing_future_market_data_stays_unevaluated(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id = _record(store)
    assert store.evaluate_observation(observation_id,future_price=None,observed_at="2026-01-10T09:00:00+00:00",trading_days_elapsed=5) is False
    assert store.agent_stats("fundamental") is None


def test_neutral_vote_excluded_from_accuracy_denominator(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id = _record(store, vote=0.0)
    assert store.evaluate_observation(observation_id,future_price=110,observed_at="2026-01-10T09:00:00+00:00",trading_days_elapsed=5) is True
    assert store.agent_stats("fundamental") is None


def test_insufficient_observed_history_keeps_untrained_prior(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id = _record(store)
    store.evaluate_observation(observation_id,future_price=110,observed_at="2026-01-10T09:00:00+00:00",trading_days_elapsed=5)
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    tr, source, samples = kiasha._track_record_for_agent("fundamental")
    assert source == "untrained-prior"
    assert samples == 1
    assert tr == kiasha.TRACK_RECORDS["fundamental"]


def test_sufficient_observed_history_replaces_prior(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    for i in range(MIN_OBSERVED_SAMPLES):
        generated = datetime(2025, 1, 1, 9, tzinfo=timezone.utc) + timedelta(days=i)
        observation_id = store.record_recommendation(code=str(i),symbol=f"نماد{i}",generated_at=generated.isoformat(),reference_price=100,kiasha_call="BUY",weighted_score=0.4,breakdown=_breakdown(1.0),horizon_trading_days=5)
        assert store.evaluate_observation(observation_id,future_price=110,observed_at=(generated+timedelta(days=7)).isoformat(),trading_days_elapsed=5)
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    tr, source, samples = kiasha._track_record_for_agent("fundamental")
    assert source == "observed"
    assert samples == MIN_OBSERVED_SAMPLES
    assert tr.lifetime_calls == MIN_OBSERVED_SAMPLES
    assert tr.accuracy == 1.0


def test_no_history_keeps_untrained_prior(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    tr, source, samples = kiasha._track_record_for_agent("fundamental")
    assert source == "untrained-prior"
    assert samples == 0
    assert tr == kiasha.TRACK_RECORDS["fundamental"]
