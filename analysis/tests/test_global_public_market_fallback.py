from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany
from global_markets.universe import _ordinary_equity_row
from global_markets.yahoo_chart import YahooChartMarketProvider


def _payload(*, exchange="NMS", currency="USD", closes=(100.0, 102.0, 101.0, 104.0)):
    timestamps = [1789401600, 1789488000, 1789574400, 1789660800]
    highs = [value + 1 for value in closes]
    lows = [value - 1 for value in closes]
    volumes = [1000, 1200, 1100, 1500]
    return {
        "chart": {
            "error": None,
            "result": [{
                "meta": {"exchangeName": exchange, "currency": currency},
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{"close": list(closes), "high": highs, "low": lows, "volume": volumes}],
                    "adjclose": [{"adjclose": list(closes)}],
                },
            }],
        }
    }


def test_public_market_fallback_enriches_us_history(monkeypatch):
    provider = YahooChartMarketProvider()
    monkeypatch.setattr(provider, "_get", lambda symbol: _payload())
    company = GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD",
        ticker="AAPL", name="Apple Inc.",
    )

    enriched = provider.enrich_market(company)

    assert enriched.price == 104.0
    assert enriched.price_observed_at
    assert enriched.price_52w_high == 105.0
    assert enriched.price_52w_low == 99.0
    assert enriched.volume_today == 1500.0
    assert enriched.avg_volume_30d == 1200.0
    assert enriched.volatility_annualized_pct is not None
    assert enriched.raw_provider_fields["public_market_vendor_symbol"] == "AAPL"
    assert any(source.provider == "yahoo-public-chart" for source in enriched.sources)
    assert any("market_history" in source.source_type for source in enriched.sources)


def test_public_market_fallback_normalizes_lse_pence_to_gbp(monkeypatch):
    provider = YahooChartMarketProvider()
    monkeypatch.setattr(
        provider,
        "_get",
        lambda symbol: _payload(exchange="LSE", currency="GBp", closes=(250.0, 255.0, 260.0, 262.0)),
    )
    company = GlobalCompany(
        country="GB", exchange="LSE", mic_code="XLON", currency="GBP",
        ticker="VOD", name="Vodafone Group Plc",
    )

    enriched = provider.enrich_market(company)

    assert enriched.currency == "GBP"
    assert enriched.price == 2.62
    assert enriched.price_52w_high == 2.63
    assert enriched.raw_provider_fields["public_market_vendor_symbol"] == "VOD.L"
    assert enriched.raw_provider_fields["public_market_price_scale"] == 0.01


def test_catalog_rejects_debt_and_foreign_secondary_lines():
    oslo = get_exchange("NO", "EURONEXT_OSLO")
    lse = get_exchange("GB", "LSE")

    assert _ordinary_equity_row(
        country="NO", spec=oslo,
        row={"type": "Common Stock", "name": "Equinor ASA"},
        symbol="EQNR", currency="NOK",
    )
    assert not _ordinary_equity_row(
        country="NO", spec=oslo,
        row={"type": "Common Stock", "name": "Aasen Spb 22/27 FRN"},
        symbol="AASB31.PR.RO", currency="NOK",
    )
    assert not _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Alcon Inc."},
        symbol="0A0D", currency="CHF",
    )
    assert _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Shell plc"},
        symbol="SHEL", currency="GBP",
    )
