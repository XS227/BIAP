from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany
from global_markets.universe import TwelveDataUniverseProvider, _ordinary_equity_row
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


def _catalog_row(symbol: str, name: str, *, mic="XNAS", currency="USD"):
    return {
        "symbol": symbol,
        "name": name,
        "currency": currency,
        "mic_code": mic,
        "type": "Common Stock",
        "cfi_code": "ESVUFR",
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


def test_catalog_rejects_debt_structured_and_foreign_secondary_lines():
    oslo = get_exchange("NO", "EURONEXT_OSLO")
    lse = get_exchange("GB", "LSE")

    assert _ordinary_equity_row(
        country="NO", spec=oslo,
        row={"type": "Common Stock", "name": "Equinor ASA", "cfi_code": "ESVUFR"},
        symbol="EQNR", currency="NOK",
    )
    # Numeric tickers are valid on Oslo and must not be rejected globally.
    assert _ordinary_equity_row(
        country="NO", spec=oslo,
        row={"type": "Common Stock", "name": "2020 Bulkers Ltd.", "cfi_code": "ESVUFR"},
        symbol="2020", currency="NOK",
    )
    assert not _ordinary_equity_row(
        country="NO", spec=oslo,
        row={"type": "Common Stock", "name": "Aasen Spb 22/27 FRN"},
        symbol="AASB31.PR.RO", currency="NOK",
    )
    # A supplied non-equity CFI wins over a loose Common Stock text label.
    assert not _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Structured Note", "cfi_code": "DBFSGR"},
        symbol="ABC1", currency="GBP",
    )
    # Numeric-leading XLON symbols are typically international/structured
    # secondary lines and are outside Kiasha's ordinary London stock universe.
    assert not _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Alcon Inc.", "cfi_code": "ESVUFR"},
        symbol="0A0D", currency="GBP",
    )
    assert not _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Morgan Stanley B.V.", "cfi_code": "ESVUFR"},
        symbol="1HP5", currency="GBP",
    )
    assert _ordinary_equity_row(
        country="GB", spec=lse,
        row={"type": "Common Stock", "name": "Shell plc", "cfi_code": "ESVUFR"},
        symbol="SHEL", currency="GBP",
    )


def test_universe_pager_does_not_treat_page_count_as_total(monkeypatch):
    provider = TwelveDataUniverseProvider(api_key="demo", max_rows=10)
    pages = {
        1: {"count": 3, "data": [
            _catalog_row("AAPL", "Apple Inc."),
            _catalog_row("ADBE", "Adobe Inc."),
            _catalog_row("AMZN", "Amazon.com Inc."),
        ]},
        2: {"count": 2, "data": [
            _catalog_row("MSFT", "Microsoft Corp."),
            _catalog_row("NVDA", "NVIDIA Corp."),
        ]},
        3: {"count": 0, "data": []},
    }
    monkeypatch.setattr(
        provider,
        "_get_page",
        lambda *, country, spec, page, outputsize: pages.get(page, {"count": 0, "data": []}),
    )

    rows = list(provider.list_instruments(country="US", exchange="NASDAQ"))

    assert [row.ticker for row in rows] == ["AAPL", "ADBE", "AMZN", "MSFT", "NVDA"]


def test_exact_aapl_search_uses_stocks_lookup_before_symbol_search(monkeypatch):
    provider = TwelveDataUniverseProvider(api_key="demo")
    calls: list[str] = []

    def fake_request(params, *, endpoint="stocks"):
        calls.append(endpoint)
        if endpoint == "stocks":
            return {"count": 1, "data": [
                _catalog_row("AAPL", "Apple Inc.", mic="XNGS"),
            ], "status": "ok"}
        return {"data": [], "status": "ok"}

    monkeypatch.setattr(provider, "_request", fake_request)

    rows = provider.search_instruments(country="US", exchange="NASDAQ", query="AAPL", limit=20)

    assert rows and rows[0].ticker == "AAPL"
    assert rows[0].mic_code == "XNGS"
    assert calls[0] == "stocks"
