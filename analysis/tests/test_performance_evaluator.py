from datetime import date, datetime, timedelta, timezone

from performance_evaluator import DailyClose, evaluate_pending, parse_daily_history, select_horizon_close
from performance_store import PerformanceStore


def _record(store, when, *, code="123", symbol="فولاد", price=100.0):
    return store.record_recommendation(
        code=code,
        symbol=symbol,
        generated_at=when.isoformat(),
        reference_price=price,
        kiasha_call="BUY",
        weighted_score=0.4,
        breakdown=[{"agent": "fundamental", "vote": 1.0, "confidence": 0.8}],
        horizon_trading_days=5,
    )


def test_parse_daily_history_filters_invalid_rows_and_sorts():
    payload = {
        "closingPriceDaily": [
            {"dEven": 20260108, "pClosing": 108},
            {"dEven": 20260105, "pClosing": 105},
            {"dEven": "bad", "pClosing": 999},
            {"dEven": 20260106, "pClosing": 0},
            {"dEven": 20260107, "pDrCotVal": 107},
        ]
    }
    history = parse_daily_history(payload)
    assert history == [
        DailyClose(date(2026, 1, 5), 105.0),
        DailyClose(date(2026, 1, 7), 107.0),
        DailyClose(date(2026, 1, 8), 108.0),
    ]


def test_horizon_counts_trading_sessions_not_calendar_days():
    generated = "2026-01-01T09:00:00+00:00"
    history = [
        DailyClose(date(2026, 1, 1), 100),  # same day: deliberately excluded
        DailyClose(date(2026, 1, 3), 101),
        DailyClose(date(2026, 1, 6), 102),
        DailyClose(date(2026, 1, 8), 103),
        DailyClose(date(2026, 1, 10), 104),
        DailyClose(date(2026, 1, 13), 105),
    ]
    target = select_horizon_close(history, generated_at=generated, horizon_trading_days=5)
    assert target == DailyClose(date(2026, 1, 13), 105)


def test_horizon_waits_when_fewer_than_required_sessions_exist():
    history = [DailyClose(date(2026, 1, day), 100 + day) for day in (2, 3, 4, 5)]
    assert select_horizon_close(
        history,
        generated_at="2026-01-01T09:00:00+00:00",
        horizon_trading_days=5,
    ) is None


def test_evaluate_pending_uses_fifth_future_trading_close(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    observation_id = _record(store, datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
    history = [
        DailyClose(date(2026, 1, 2), 101),
        DailyClose(date(2026, 1, 3), 102),
        DailyClose(date(2026, 1, 6), 103),
        DailyClose(date(2026, 1, 7), 104),
        DailyClose(date(2026, 1, 8), 110),
    ]
    summary = evaluate_pending(store, history_fetcher=lambda _code: history)
    assert summary["evaluated"] == 1
    assert summary["errors"] == 0
    assert store.pending_observations() == []
    stats = store.agent_stats("fundamental")
    assert stats is not None
    assert stats.evaluated_calls == 1
    assert stats.directional_accuracy == 1.0
    with store._connect() as conn:
        row = conn.execute(
            "SELECT future_price, trading_days_elapsed FROM recommendation_observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
    assert row["future_price"] == 110.0
    assert row["trading_days_elapsed"] == 5


def test_evaluate_pending_leaves_missing_history_pending(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    _record(store, datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
    summary = evaluate_pending(store, history_fetcher=lambda _code: [])
    assert summary["evaluated"] == 0
    assert summary["waiting"] == 1
    assert summary["errors"] == 0
    assert len(store.pending_observations()) == 1


def test_evaluate_pending_network_error_does_not_guess_or_abort_batch(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    when = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    _record(store, when, code="111", symbol="الف")
    _record(store, when, code="222", symbol="ب")

    def fetch(code):
        if code == "111":
            raise TimeoutError("upstream unavailable")
        return [
            DailyClose(date(2026, 1, 2), 101),
            DailyClose(date(2026, 1, 3), 102),
            DailyClose(date(2026, 1, 4), 103),
            DailyClose(date(2026, 1, 5), 104),
            DailyClose(date(2026, 1, 6), 105),
        ]

    summary = evaluate_pending(store, history_fetcher=fetch)
    assert summary["evaluated"] == 1
    assert summary["errors"] == 1
    assert len(store.pending_observations()) == 1


def test_same_code_history_fetched_once_for_multiple_pending_rows(tmp_path):
    store = PerformanceStore(str(tmp_path / "perf.sqlite3"))
    _record(store, datetime(2026, 1, 1, 9, tzinfo=timezone.utc), code="123", symbol="فولاد")
    _record(store, datetime(2026, 1, 2, 9, tzinfo=timezone.utc), code="123", symbol="فولاد")
    calls = []
    history = [
        DailyClose(date(2026, 1, day), 100 + day)
        for day in (3, 4, 5, 6, 7, 8, 9)
    ]

    def fetch(code):
        calls.append(code)
        return history

    evaluate_pending(store, history_fetcher=fetch)
    assert calls == ["123"]
