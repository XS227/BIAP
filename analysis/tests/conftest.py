import sys
from pathlib import Path

import pytest

# Keep analysis modules importable whether pytest is launched from the repo
# root or from the analysis directory.
ANALYSIS_DIR = Path(__file__).resolve().parents[1]
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

import agents
import kiasha
from performance_store import PerformanceStore


@pytest.fixture(autouse=True)
def _external_tsetmc_enrichment_disabled_by_default(monkeypatch):
    """Prevent any test from making a real, slow TSETMC network call.

    agents.risk_agent() -> _verified_market_enrichment() calls
    fetch_verified_enrichment() (a real HTTP request, min 12s timeout, tried
    twice = up to ~24s) for any company without pre-populated Tindex data --
    which includes every mock/test company. Any test that reaches
    kiasha.decide()/agents.run_team() without disabling this (order-flow,
    admin, regression tests -- none of which are testing TSETMC enrichment
    itself) would otherwise hang for tens of seconds per call, and the whole
    suite for many minutes, whenever the live upstream is unreachable from
    this host. test_extended_market_field.py already isolated itself this
    exact way per-test; this makes that the default everywhere. Tests that
    actually exercise real enrichment override this via monkeypatch.
    """
    monkeypatch.setattr(agents, "fetch_verified_enrichment", lambda _symbol: {})


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
