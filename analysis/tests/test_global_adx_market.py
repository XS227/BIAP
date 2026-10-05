from __future__ import annotations

import pytest

from global_markets.adx_market import ADXOfficialMarketProvider, parse_adx_recent_trades
from global_markets.models import GlobalCompany


def test_parse_adx_recent_trades_orders_valid_rows():
    rows = parse_adx_recent_trades({
        "resultCode":"S",
        "response":{"results":[
            {"date":"2026-09-25","open":8.16,"low":8.14,"high":8.26,"close":8.17,"volume":13696360},
            {"date":"2026-09-24","open":8.07,"low":8.01,"high":8.25,"close":8.16,"volume":13016044},
        ]},
    })
    assert [r["date"] for r in rows] == ["2026-09-24","2026-09-25"]
    assert rows[-1]["close"] == pytest.approx(8.17)


def test_adx_market_provider_enriches_official_quote(monkeypatch):
    provider=ADXOfficialMarketProvider()
    overview={
        "resultCode":"S",
        "response":{"overview":{
            "companyISIN":"AEA002001013","companySymbol":"ALDAR","previousClose":8.16,
            "volume":13696360,"open":8.16,"high":8.26,"low":8.14,
            "52weekHigh":11.8,"52weekLow":6.97,"tradingState":"Normal Trading (Active)",
            "marketCap":64237683857,"bid":8.15,"ask":8.25,"last":8.17,
            "boardId":"Main Market","issuedShares":7862629603,
        }}
    }
    recent={
        "resultCode":"S",
        "response":{"results":[
            {"date":"2026-09-25","open":8.16,"low":8.14,"high":8.26,"close":8.17,"value":112386440.79,"volume":13696360,"trades":1658},
            {"date":"2026-09-24","open":8.07,"low":8.01,"high":8.25,"close":8.16,"value":105842464.36,"volume":13016044,"trades":1594},
        ]}
    }
    monkeypatch.setattr(provider,"_get",lambda path: recent if "recentTrades" in path else overview)
    monkeypatch.setattr("global_markets.adx_market.persist_daily_history",lambda *a,**k: None)
    seed=GlobalCompany(country="AE",exchange="ADX",currency="AED",ticker="ALDAR",name="Aldar Properties PJSC",mic_code="XADS")
    company=provider.enrich_market(seed)
    assert company.price == pytest.approx(8.17)
    assert company.market_cap == pytest.approx(64237683857)
    assert company.shares_outstanding == pytest.approx(7862629603)
    assert company.price_52w_high == pytest.approx(11.8)
    assert company.price_52w_low == pytest.approx(6.97)
    assert company.volume_today == pytest.approx(13696360)
    assert company.price_observed_at.startswith("2026-09-24T20:00:00")
    assert company.isin == "AEA002001013"
    assert any(s.provider=="official-adx-company-market" for s in company.sources)
    assert company.sources[-1].source_type=="official_exchange_market_history"
