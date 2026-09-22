from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics, _source_plan_payload, _supported_operating_equity
from global_markets.source_cache import write_json_atomic


def test_safe_valuation_derivations_use_verified_inputs_only():
    company = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="TEST",
        name="Test Operating Company",
        price=50.0,
        reporting_currency="USD",
        shares_outstanding=100_000_000,
        total_equity=2_000_000_000,
        eps=5.0,
        total_debt=300_000_000,
        cash_and_equivalents=100_000_000,
        ebitda=600_000_000,
        dividend_per_share=1.0,
    )
    enriched = _derive_metrics(company)
    assert enriched.market_cap == 5_000_000_000
    assert enriched.book_value_per_share == 20.0
    assert enriched.pe == 10.0
    assert enriched.pb == 2.5
    assert enriched.dividend_yield_pct == 2.0
    assert round(enriched.ev_ebitda, 4) == round(5_200_000_000 / 600_000_000, 4)
    assert "pe=price/eps" in enriched.raw_provider_fields["derived_metrics"]


def test_cross_currency_listing_does_not_mix_filing_eps_with_quote_price():
    company = GlobalCompany(
        country="SE",
        exchange="NASDAQ_STOCKHOLM",
        mic_code="XSTO",
        currency="SEK",
        ticker="TEST",
        name="Test AB",
        price=100.0,
        reporting_currency="EUR",
        shares_outstanding=10_000_000,
        total_equity=500_000_000,
        eps=3.0,
    )
    enriched = _derive_metrics(company)
    assert enriched.market_cap == 1_000_000_000
    assert enriched.pe is None
    assert enriched.pb is None
    assert enriched.book_value_per_share is None


def test_direct_analysis_guard_rejects_leveraged_certificate_name():
    company = GlobalCompany(
        country="SE",
        exchange="NASDAQ_STOCKHOLM",
        mic_code="XSTO",
        currency="SEK",
        ticker="BULL.VOLV.X2.H",
        name="BULL VOLV X2 H",
    )
    assert _supported_operating_equity(company) is False


def test_market_ready_source_plan_is_explicitly_not_runtime_configured():
    plan = _source_plan_payload("CA")
    assert plan["status"] == "market-ready"
    assert plan["runtimeConfigured"] is False
    assert "not connected" in plan["runtimeNote"].lower()


def test_japan_source_plan_reflects_edinet_key(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    assert _source_plan_payload("JP")["runtimeConfigured"] is False
    monkeypatch.setenv("BIAP_EDINET_API_KEY", "configured")
    assert _source_plan_payload("JP")["runtimeConfigured"] is True


def test_recent_market_scan_supplies_non_official_peer_pe_benchmark(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    scan_path = tmp_path / "scan-cache" / "US" / "NASDAQ.json"
    peers = []
    for index, pe in enumerate((18.0, 20.0, 22.0, 24.0, 26.0), start=1):
        peers.append({
            "ticker": f"P{index}",
            "company": {
                "ticker": f"P{index}",
                "sector": "Technology",
                "pe": pe,
            },
        })
    write_json_atomic(scan_path, {
        "schemaVersion": 1,
        "cachedAt": "2026-09-22T00:00:00+00:00",
        "payload": {"deepResults": peers},
    })

    from global_markets import service as service_module
    class _FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2026, 9, 22, 1, tzinfo=tz)
        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime
            return datetime.fromisoformat(value)
    monkeypatch.setattr(service_module, "datetime", _FixedDateTime)

    company = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="AAPL",
        name="Apple Inc.",
        sector="Technology",
        price=200.0,
        reporting_currency="USD",
        eps=10.0,
    )
    enriched = _derive_metrics(company)
    assert enriched.sector_pe == 22.0
    assert enriched.raw_provider_fields["peer_pe_benchmark_scope"] == "same_sector_scan_median"
    assert enriched.raw_provider_fields["peer_pe_benchmark_count"] == 5
    assert any(source.provider == "biap-derived-metrics" for source in enriched.sources)
