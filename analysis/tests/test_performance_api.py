from datetime import datetime, timedelta, timezone

import api_server
import performance_routes as routes
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore


def _record(store: PerformanceStore, *, symbol="فولاد", vote=1.0, day=1):
    generated = datetime(2026, 1, day, 9, tzinfo=timezone.utc)
    observation_id = store.record_recommendation(
        code="46348559193224090",
        symbol=symbol,
        generated_at=generated.isoformat(),
        reference_price=100.0,
        kiasha_call="BUY",
        weighted_score=0.4,
        breakdown=[{"agent": "fundamental", "vote": vote, "confidence": 0.8}],
        horizon_trading_days=5,
    )
    return observation_id, generated


def test_performance_routes_are_mounted():
    # app.routes may contain Starlette's internal _IncludedRouter entries that do
    # not expose .path. OpenAPI is the stable public view of mounted HTTP paths.
    paths = set(api_server.app.openapi()["paths"])
    assert "/performance/summary" in paths
    assert "/performance/agents" in paths


def test_summary_reports_pending_without_inventing_accuracy(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    _record(store)
    monkeypatch.setattr(routes, "STORE", store)

    payload = routes.performance_summary()

    assert payload["pendingRecommendations"] == 1
    assert payload["evaluatedRecommendationsLowerBound"] == 0
    assert payload["observedTrustActive"] is False
    fundamental = next(item for item in payload["agents"] if item["agent"] == "fundamental")
    assert fundamental["evaluatedCalls"] == 0
    assert fundamental["directionalAccuracy"] is None
    assert fundamental["trustReady"] is False


def test_agents_reports_real_evaluated_statistics(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id, generated = _record(store)
    assert store.evaluate_observation(
        observation_id,
        future_price=110.0,
        observed_at=(generated + timedelta(days=7)).isoformat(),
        trading_days_elapsed=5,
    )
    monkeypatch.setattr(routes, "STORE", store)

    payload = routes.performance_agents()

    fundamental = next(item for item in payload["items"] if item["agent"] == "fundamental")
    assert fundamental["evaluatedCalls"] == 1
    assert fundamental["directionalAccuracy"] == 1.0
    assert round(fundamental["averageSignedReturn"], 6) == 0.1
    assert fundamental["returnStd"] == 0.0
    assert fundamental["lastUpdated"] is not None
    assert fundamental["trustReady"] is False
    assert fundamental["minimumObservedSamples"] == MIN_OBSERVED_SAMPLES
    assert payload["observedTrustEnabledFor"] == []


def test_summary_never_claims_observed_trust_before_threshold(tmp_path, monkeypatch):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    start = datetime(2025, 1, 1, 9, tzinfo=timezone.utc)
    for i in range(3):
        observation_id = store.record_recommendation(
            code=str(i),
            symbol=f"نماد{i}",
            generated_at=(start + timedelta(days=i)).isoformat(),
            reference_price=100.0,
            kiasha_call="BUY",
            weighted_score=0.4,
            breakdown=[{"agent": "fundamental", "vote": 1.0, "confidence": 0.8}],
            horizon_trading_days=5,
        )
        assert store.evaluate_observation(
            observation_id,
            future_price=105.0,
            observed_at=(start + timedelta(days=i + 7)).isoformat(),
            trading_days_elapsed=5,
        )
    monkeypatch.setattr(routes, "STORE", store)

    payload = routes.performance_summary()

    assert payload["evaluatedRecommendationsLowerBound"] == 3
    assert payload["observedTrustActive"] is False
    fundamental = next(item for item in payload["agents"] if item["agent"] == "fundamental")
    assert fundamental["evaluatedCalls"] == 3
    assert fundamental["trustReady"] is False
