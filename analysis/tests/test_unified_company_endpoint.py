import api_server


def test_company_dataset_exposes_normalized_sources_without_ai(monkeypatch):
    company = {
        "ticker": "46348559193224090",
        "name_fa": "فولاد",
        "name_en": None,
        "data_available": {
            "codal": True,
            "codal_metadata": True,
            "market_extended": True,
            "tindex": True,
            "market_memory": False,
        },
        "codal": {"revenue_yoy_pct": 18.4, "net_margin_pct": 24.1},
        "codal_metadata": {"company_name": "فولاد مبارکه اصفهان"},
        "tindex": {"volatility": 0.29},
        "market_memory": None,
        "market": {
            "price": 6850.0,
            "last_price": 6850.0,
            "closing_price": 6810.0,
            "change_percent": 2.23,
            "tindex_performance": {"return_6m": 19.6, "volatility": 0.29},
            "tindex_flow": {"retail_net": 125_000_000_000.0},
        },
    }
    monkeypatch.setattr(api_server, "_require_warm_ready", lambda: None)
    monkeypatch.setattr(api_server, "_company_or_404", lambda _code: (company, "live"))

    payload = api_server.company_dataset("فولاد")

    assert payload["dataSource"] == "live"
    assert payload["identity"]["nameFa"] == "فولاد"
    assert payload["market"]["price"] == 6850.0
    assert payload["financials"]["revenue_yoy_pct"] == 18.4
    assert payload["performance"]["return_6m"] == 19.6
    assert payload["flow"]["retail_net"] == 125_000_000_000.0
    assert payload["provenance"] == {
        "sources": ["tsetmc", "codal", "tindex"],
        "primary": "tsetmc",
        "isLive": True,
        "syntheticValues": False,
    }
