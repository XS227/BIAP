from market_data import LiveQuote
import company_builder


def test_live_quote_merges_codal_tindex_and_tsetmc_without_fabrication(monkeypatch):
    quote = LiveQuote(
        code="46348559193224090",
        name="فولاد",
        last_price=6850.0,
        closing_price=6810.0,
        yesterday_price=6700.0,
        change=150.0,
        change_percent=2.2388,
    )

    monkeypatch.setattr(
        company_builder,
        "_codal_parts",
        lambda _symbol: (
            {"symbol": "فولاد", "company_name": "فولاد مبارکه اصفهان"},
            {
                "symbol": "فولاد",
                "revenue_yoy_pct": 18.4,
                "net_margin_pct": 24.1,
                "report_scope": "consolidated",
            },
        ),
    )
    monkeypatch.setattr(company_builder, "fetch_extended_market_data", lambda _code: None)
    monkeypatch.setattr(
        company_builder,
        "_tindex_dict",
        lambda _symbol: {
            "price": 6840.0,
            "change_percent": 2.1,
            "pe": 7.2,
            "market_cap": 410_000_000_000_000.0,
            "shares_issued": 60_000_000_000.0,
            "sector": "فلزات اساسی",
            "range_52w_low": 5100.0,
            "range_52w_high": 7600.0,
            "return_1w": 1.4,
            "return_1m": 5.2,
            "return_3m": 11.8,
            "return_6m": 19.6,
            "return_1y": 31.5,
            "return_3y": 84.0,
            "volatility": 0.29,
            "max_drawdown": -0.18,
            "range_52w_position": 0.70,
            "avg_trade_value_30d": 2_300_000_000_000.0,
            "retail_net": 125_000_000_000.0,
            "institutional_net": -125_000_000_000.0,
            "buy_per_capita": 42_000_000.0,
            "sell_per_capita": 38_000_000.0,
            "float_percent": 27.5,
        },
    )

    company = company_builder.build_company_from_quote(quote)

    assert company["data_available"]["codal"] is True
    assert company["data_available"]["codal_metadata"] is True
    assert company["data_available"]["tindex"] is True
    assert company["data_available"]["market_extended"] is False

    # TSETMC live quote remains authoritative for the live price/change.
    assert company["market"]["price"] == 6850.0
    assert company["market"]["change_percent"] == 2.2388

    # Tindex fills fields that are unavailable from the live quote.
    assert company["market"]["pe"] == 7.2
    assert company["market"]["price_52w_low"] == 5100.0
    assert company["market"]["price_52w_high"] == 7600.0
    assert company["market"]["sector_name"] == "فلزات اساسی"
    assert company["market"]["tindex_performance"]["volatility"] == 0.29
    assert company["market"]["tindex_flow"]["retail_net"] == 125_000_000_000.0
    assert company["market"]["float_percent"] == 27.5

    # CODAL stays available as its own verified fundamental block.
    assert company["codal"]["revenue_yoy_pct"] == 18.4
    assert company["codal"]["net_margin_pct"] == 24.1

    # Missing TSETMC extended fields stay missing; no synthetic values are created.
    assert company["market"]["day_high"] is None
    assert company["market"]["volume_today"] is None


def test_symbol_dataset_keeps_missing_sources_explicit(monkeypatch):
    monkeypatch.setattr(company_builder, "_codal_parts", lambda _symbol: ({"company_name": "نمونه"}, None))
    monkeypatch.setattr(company_builder, "_tindex_dict", lambda _symbol: None)

    company = company_builder.build_company_from_symbol("نمونه")

    assert company is not None
    assert company["data_available"] == {
        "codal": False,
        "codal_metadata": True,
        "market_extended": False,
        "tindex": False,
        "market_memory": False,
    }
    assert company["market"]["price"] is None
    assert company["market"]["pe"] is None
