from __future__ import annotations

import pytest
from fastapi import HTTPException

import global_routes
from global_markets.models import GlobalCompany


class _Registry:
    def __init__(self, provider):
        self._provider = provider

    def universe(self, country, exchange):
        return self._provider


class _OfficialProvider:
    class _Upstream:
        provider_id = "official-test-us-universe"

    upstream = _Upstream()

    def search_instruments(self, **kwargs):
        return []

    def list_instruments(self, **kwargs):
        return []


class _OutageProvider(_OfficialProvider):
    def list_instruments(self, **kwargs):
        raise RuntimeError("upstream down")


def test_analyze_seed_rejects_ticker_not_on_selected_official_exchange(monkeypatch):
    monkeypatch.setattr(global_routes, "build_registry", lambda: _Registry(_OfficialProvider()))
    req = global_routes.InstrumentRequest(
        country="US",
        exchange="NASDAQ",
        ticker="QBTS",
        name="D-Wave Quantum Inc.",
        currency="USD",
    )
    with pytest.raises(HTTPException) as exc:
        global_routes._seed(req)
    assert exc.value.status_code == 400
    assert "not listed in the official US/NASDAQ universe" in str(exc.value.detail)


def test_analyze_seed_keeps_legacy_fallback_only_for_real_provider_outage(monkeypatch):
    monkeypatch.setattr(global_routes, "build_registry", lambda: _Registry(_OutageProvider()))
    req = global_routes.InstrumentRequest(
        country="US",
        exchange="NASDAQ",
        ticker="AAPL",
        name="Apple Inc.",
        currency="USD",
    )
    seed = global_routes._seed(req)
    assert seed.ticker == "AAPL"
    assert seed.exchange == "NASDAQ"
