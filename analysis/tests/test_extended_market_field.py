import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import agents
import api_server
from market_data import LiveQuote

_FULL_MARKET = {
    "price": 2698.0,
    "last_price": 2698.0,
    "closing_price": 2697.0,
    "yesterday_price": 2620.0,
    "change": 78.0,
    "change_percent": 2.94,
    "day_low": 2650.0,
    "day_high": 2710.0,
    "volume_today": 12_000_000,
    "trade_value_today": 32_000_000_000,
    "trade_count_today": 4200,
    "avg_volume_30d": 9_000_000,
    "price_52w_high": 4500.0,
    "price_52w_low": 1600.0,
    "estimated_eps": None,
    "eps_value": 517,
    "pe": 5.21,
    "sector_avg_pe": 11.08,
    "shares_outstanding": 1_000_000_000,
    "market_cap": 2_698_000_000_000,
    "market_cap_bn": 2698.0,
    "base_volume": 5_000_000,
    "sector_code": "27",
    "sector_name": "Basic Metals",
    "market_flow": 1,
    "market_title": "Bourse",
    "valuation_source": "tsetmc_instrument_info",
}


def _disable_external_enrichment(monkeypatch):
    """Endpoint contract tests must never depend on TSETMC/network availability."""
    monkeypatch.setattr(agents, "fetch_verified_enrichment", lambda _symbol: {})


def test_recommendation_endpoint_exposes_extended_market_fields(monkeypatch):
    _disable_external_enrichment(monkeypatch)
    quote = LiveQuote(
        code="46348559193224090", name="فولاد", last_price=2698.0,
        closing_price=2697.0, yesterday_price=2620.0, change=78.0, change_percent=2.94,
    )
    monkeypatch.setattr(api_server, "find_quote", lambda code: quote)
    monkeypatch.setattr(
        api_server,
        "build_company_from_quote",
        lambda q, *, codal_symbol=None: {
            "ticker": q.code,
            "name_fa": q.name,
            "codal": None,
            "codal_metadata": None,
            "data_available": {"codal": False, "codal_metadata": False, "market_extended": True},
            "market": dict(_FULL_MARKET),
        },
    )

    client = TestClient(api_server.app)
    response = client.get(f"/stock/recommendation/{quote.code}")
    assert response.status_code == 200
    body = response.json()

    assert body["extendedMarket"] == {
        "dayLow": 2650.0,
        "dayHigh": 2710.0,
        "volumeToday": 12_000_000,
        "tradeValueToday": 32_000_000_000,
        "tradeCountToday": 4200,
        "avgVolume30d": 9_000_000,
        "price52wHigh": 4500.0,
        "price52wLow": 1600.0,
        "pe": 5.21,
        "sectorAvgPe": 11.08,
        "epsValue": 517,
        "estimatedEps": None,
        "marketCap": 2_698_000_000_000,
        "marketCapBn": 2698.0,
        "sharesOutstanding": 1_000_000_000,
        "sectorName": "Basic Metals",
    }


def test_extended_market_is_none_for_non_live_sources(monkeypatch):
    _disable_external_enrichment(monkeypatch)
    client = TestClient(api_server.app)
    response = client.get("/stock/recommendation/SAMPLE1")
    assert response.status_code == 200
    assert response.json()["extendedMarket"] is None
