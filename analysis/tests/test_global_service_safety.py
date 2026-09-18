from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics, _source_plan_payload, _supported_operating_equity


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
    )
    enriched = _derive_metrics(company)
    assert enriched.market_cap == 5_000_000_000
    assert enriched.book_value_per_share == 20.0
    assert enriched.pe == 10.0
    assert enriched.pb == 2.5
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
    plan = _source_plan_payload("SG")
    assert plan["status"] == "market-ready"
    assert plan["runtimeConfigured"] is False
    assert "not connected" in plan["runtimeNote"].lower()


def test_japan_source_plan_reflects_edinet_key(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    assert _source_plan_payload("JP")["runtimeConfigured"] is False
    monkeypatch.setenv("BIAP_EDINET_API_KEY", "configured")
    assert _source_plan_payload("JP")["runtimeConfigured"] is True
