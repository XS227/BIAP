"""Agent routes never wait on a live download (cache-only mode), JP 5243-style instruments return a client error, and the backfill job is throttled."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import global_routes
from global_markets import filing_backfill as fb
from global_markets import offline_guard
from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError, ProviderRegistry
from global_markets.request_mode import NOT_YET_AVAILABLE, cache_only, is_cache_only


class _Upstream:
    provider_id = "fake-upstream"

    def __init__(self):
        self.calls = 0

    def enrich_fundamentals(self, company):
        self.calls += 1
        raise AssertionError("live download attempted")


def _company(ticker="ENI"):
    return GlobalCompany(country="IT", exchange="EURONEXT_MILAN", ticker=ticker, name="X", currency="EUR")


def test_cache_only_flag_is_scoped():
    assert not is_cache_only()
    with cache_only():
        assert is_cache_only()
    assert not is_cache_only()


def test_persistent_provider_does_not_call_upstream_in_cache_only(tmp_path):
    up = _Upstream()
    prov = PersistentFundamentalsProvider(up, data_dir=str(tmp_path))
    with cache_only():
        with pytest.raises(GlobalProviderError, match="data not yet available"):
            prov.enrich_fundamentals(_company())
    assert up.calls == 0
    assert prov.cache_only_safe is True


def test_registry_skips_providers_without_a_cache_layer_in_cache_only():
    class Live:
        provider_id = "live-only"
        calls = 0

        def enrich_fundamentals(self, c):
            Live.calls += 1
            return c

        def enrich_market(self, c):
            Live.calls += 1
            return c
    reg = ProviderRegistry()
    reg.register_market("IT", "EURONEXT_MILAN", Live())
    reg.register_fundamentals("IT", "EURONEXT_MILAN", Live())
    with cache_only():
        _, diag = reg.enrich_best_effort(_company())
    assert Live.calls == 0 and diag.fundamentals_status == "error" and NOT_YET_AVAILABLE[:30] in diag.fundamentals_error
    _, diag2 = reg.enrich_best_effort(_company())
    assert Live.calls == 2 and diag2.fundamentals_status == "ok"


def test_risk_route_makes_no_network_call_and_flags_missing_data(monkeypatch, tmp_path):
    """Whole route, empty data dir, outbound network blocked: any download attempt would raise NetworkBlocked."""
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BIAP_GLOBAL_ONLINE_FIRST", "0")
    monkeypatch.setattr(global_routes.risk_agent, "enabled", lambda: True)
    offline_guard.install()
    try:
        try:
            out = global_routes.global_risk(global_routes.InstrumentRequest(country="IT", exchange="EURONEXT_MILAN", ticker="ENI"))
        except HTTPException as exc:
            assert exc.status_code in (404, 422, 503) and "offline mode" not in str(exc.detail)
            return
    finally:
        offline_guard.uninstall()
    assert out["level"] is None and out["status"] == "INSUFFICIENT_DATA"
    assert out.get("dataNotYetAvailable") is True and "background job" in " ".join(out["reasons"])


def test_unsupported_instrument_is_a_client_error(monkeypatch):
    from global_markets.service import UnsupportedInstrument
    monkeypatch.setattr(global_routes.risk_agent, "enabled", lambda: True)
    monkeypatch.setattr(global_routes.performance_agent, "enabled", lambda: True)

    def boom(*a, **k):
        raise UnsupportedInstrument("5243 is not a supported ordinary operating-company equity")
    monkeypatch.setattr("global_markets.service._evaluate", boom)
    monkeypatch.setattr(global_routes, "_seed", lambda req: None)
    req = global_routes.InstrumentRequest(country="JP", exchange="TSE_JP", ticker="5243")
    for handler in (global_routes.global_risk, global_routes.global_performance, global_routes.global_analyze):
        with pytest.raises(HTTPException) as e:
            handler(req)
        assert e.value.status_code == 422 and "not a supported ordinary" in e.value.detail


# --- backfill job -----------------------------------------------------------------------------------------------------------
def test_quiet_window():
    t = lambda h, m: datetime(2026, 11, 26, h, m, tzinfo=timezone.utc)
    assert fb.in_quiet_window(t(22, 45)) and fb.in_quiet_window(t(23, 59)) and fb.in_quiet_window(t(1, 59))
    assert not fb.in_quiet_window(t(2, 0)) and not fb.in_quiet_window(t(22, 44)) and not fb.in_quiet_window(t(12, 0))


class _FakeFund:
    def __init__(self, stored):
        self.stored, self.fetched = set(stored), []

    def _read(self, c):
        return {"x": 1} if c.ticker in self.stored else None

    def _is_fresh(self, p):
        return True

    def enrich_fundamentals(self, c):
        self.fetched.append(c.ticker)
        if c.ticker == "BAD":
            raise GlobalProviderError("boom")


class _FakeUniverse:
    def __init__(self, tickers):
        self.t = tickers

    def list_instruments(self, **kw):
        return [GlobalCompany(country="IT", exchange="EURONEXT_MILAN", ticker=t, name=t + " SpA", currency="EUR") for t in self.t]


class _FakeRegistry:
    def __init__(self, f, u):
        self.f, self.u = f, u

    def fundamentals(self, c, e):
        return self.f

    def universe(self, c, e):
        return self.u


noon = lambda: datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def test_backfill_fetches_only_missing_with_pause_and_cap():
    f = _FakeFund(stored={"A"})
    sleeps = []
    reg = _FakeRegistry(f, _FakeUniverse(["A", "B", "BAD", "C", "D"]))
    out = fb.backfill("IT", "EURONEXT_MILAN", registry=reg, max_fetch=3, delay=7.0, now=noon, sleep=sleeps.append)
    assert f.fetched == ["B", "BAD", "C"] and out["alreadyStored"] == 1 and out["fetched"] == 2 and out["failed"] == 1
    assert sleeps == [7.0, 7.0, 7.0] and out["stopped"].startswith("reached --max")


def test_backfill_dry_run_and_quiet_window_and_excluded_country():
    f = _FakeFund(stored=set())
    reg = _FakeRegistry(f, _FakeUniverse(["A", "B"]))
    assert fb.backfill("IT", "EURONEXT_MILAN", registry=reg, dry_run=True, now=noon)["toFetch"] == 2 and f.fetched == []
    night = lambda: datetime(2026, 11, 26, 23, 30, tzinfo=timezone.utc)
    assert fb.backfill("IT", "EURONEXT_MILAN", registry=reg, now=night)["stopped"].startswith("quiet") and f.fetched == []
    assert fb.backfill("IR", "TSE", registry=reg, now=noon)["stopped"] == "excluded country"
