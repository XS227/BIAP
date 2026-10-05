from __future__ import annotations

from dataclasses import replace
import json

import pytest

from global_markets.dfm_market import DFMOfficialMarketProvider, _chart_rows
from global_markets.models import GlobalCompany


def test_dfm_chart_rows_parse_exchange_close_history():
    payload = {
        "ChartData": json.dumps([
            {"currentIndex": "3.70", "date": "08/21/2026 00:00:00"},
            {"currentIndex": "3.72", "date": "08/24/2026 00:00:00"},
            {"currentIndex": "3.79", "date": "09/25/2026 00:00:00"},
        ])
    }
    rows = _chart_rows(payload)
    assert [x[1] for x in rows] == [3.70, 3.72, 3.79]
    assert rows[-1][0].date().isoformat() == "2026-09-25"


def test_dfm_market_provider_enriches_verified_quote(monkeypatch):
    profile = {
        "Symbol": "DIC",
        "Market": "DFM",
        "Exchange": "DFM",
        "InstrumentType": "equities",
        "Sector": "Industrials",
        "ISIN": "AED000601016",
        "IssuedShares": 4252019585,
        "LastPrice": "3.79",
        "LastTradeDate": "2026-09-25",
        "High52": "4.35",
        "Low52": "2.98",
        "MarketCap": "16,115,154,227",
        "Volume": "1,086,759",
    }
    history = [
        {"currentIndex": f"{3.40 + i * 0.005:.3f}", "date": f"07/{1 + i:02d}/2026 00:00:00"}
        for i in range(1, 22)
    ]
    history += [
        {"currentIndex": f"{3.50 + i * 0.004:.3f}", "date": f"08/{1 + i:02d}/2026 00:00:00"}
        for i in range(1, 22)
    ]
    history += [
        {"currentIndex": f"{3.60 + i * 0.009:.3f}", "date": f"09/{1 + i:02d}/2026 00:00:00"}
        for i in range(1, 23)
    ]
    trading = {
        "ChartData": json.dumps(history),
        "LastPrice": "3.79",
        "CurrentValue": "3.79",
        "LastTradeDate": "2026-09-25",
        "Volume": "1,086,759",
        "MarketCap": "16,115,154,227",
        "High52": "4.35",
        "Low52": "2.98",
        "PreviousClose": "3.77",
    }

    provider = DFMOfficialMarketProvider()
    calls = []

    def fake_post(body: str):
        calls.append(body)
        return profile if "companyprofile" in body else trading

    monkeypatch.setattr(provider, "_post", fake_post)
    monkeypatch.setattr("global_markets.dfm_market.persist_daily_history", lambda *a, **k: None)

    seed = GlobalCompany(
        country="AE",
        exchange="DFM",
        currency="AED",
        ticker="DIC",
        name="Dubai Investments PJSC",
        mic_code="XDFM",
    )
    company = provider.enrich_market(seed)

    assert company.price == pytest.approx(3.79)
    assert company.currency == "AED"
    assert company.market_cap == pytest.approx(16_115_154_227)
    assert company.shares_outstanding == 4_252_019_585
    assert company.price_52w_high == pytest.approx(4.35)
    assert company.price_52w_low == pytest.approx(2.98)
    assert company.volume_today == pytest.approx(1_086_759)
    assert company.return_1m_pct is not None
    assert company.return_3m_pct is not None
    assert company.return_6m_pct is None
    assert company.price_observed_at.startswith("2026-09-24T20:00:00")
    assert any(source.provider == "official-dfm-company-market" for source in company.sources)
    assert company.sources[-1].source_type == "official_exchange_market_history"
    assert len(calls) == 2
