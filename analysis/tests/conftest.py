import pytest

import kiasha
from performance_store import PerformanceStore


@pytest.fixture(autouse=True)
def _isolated_performance_store(tmp_path, monkeypatch):
    """Prevent any test from writing into the real production performance DB.

    kiasha.decide() records every call into performance_store.py's default
    (production) SQLite file unless kiasha._performance_store is overridden.
    Tests that exercise decide()/the recommendation pipeline without
    overriding it (e.g. via api_server's TestClient) would otherwise leave
    fixture rows like TSE1/IFB1/BASE1/SAMPLE1 in biap_performance.sqlite3.
    Tests that need their own store still override this via monkeypatch.
    """
    store = PerformanceStore(str(tmp_path / "test_performance.sqlite3"))
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    yield store


@pytest.fixture(autouse=True)
def _market_session_check_disabled_by_default(monkeypatch):
    """Keep order-flow tests deterministic regardless of wall-clock time.

    risk.load_policy() defaults to enforcing TSE trading hours/days, which
    depends on the real current time -- any test that exercises
    /orders/preview through the real policy (not risk.py's own dedicated
    tests, which call evaluate_order_risk() directly with an explicit
    policy/now) would otherwise pass or fail depending on when it happens
    to run. Dedicated market-session tests override this back with their
    own explicit policy, never through this env var.
    """
    monkeypatch.setenv("BIAP_ENFORCE_MARKET_SESSION", "false")
