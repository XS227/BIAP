from __future__ import annotations

import pytest

from global_markets.agents import evidence_agent
from global_markets.country_packs import get_exchange
from global_markets.gleif import GLEIFResolver, LEIResolution
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import GlobalProviderError
from global_markets.yahoo_fundamentals import YahooFundamentalsProvider


def _resolution(lei: str, name: str) -> LEIResolution:
    return LEIResolution(
        lei=lei,
        legal_name=name,
        entity_status="ACTIVE",
        registration_status="ISSUED",
        source_url=f"https://api.gleif.org/api/v1/lei-records/{lei}",
    )


def test_spain_and_japan_use_vendor_supported_primary_mics():
    spain = get_exchange("ES", "BME_MADRID")
    japan = get_exchange("JP", "TSE_JP")

    assert spain.mic == "XMAD"
    assert "BMEX" in spain.accepted_mics
    assert japan.mic == "XJPX"
    assert "XTKS" in japan.accepted_mics


def test_gleif_accepts_unique_legal_form_spelling_variant(monkeypatch):
    resolver = GLEIFResolver()
    ryanair = _resolution("635400L2CWET7ONOBJ04", "RYANAIR HOLDINGS PUBLIC LIMITED COMPANY")

    def fake_search(text: str, *, page_size: int = 100):
        return [] if text == "Ryanair Holdings plc" else [ryanair]

    monkeypatch.setattr(resolver, "_search", fake_search)

    result = resolver.resolve_exact_legal_name("Ryanair Holdings plc")
    assert result.lei == ryanair.lei


def test_gleif_rejects_ambiguous_legal_form_normalized_matches(monkeypatch):
    resolver = GLEIFResolver()
    one = _resolution("11111111111111111111", "Example Holdings Public Limited Company")
    two = _resolution("22222222222222222222", "Example Holdings PLC")

    def fake_search(text: str, *, page_size: int = 100):
        return [] if text == "Example Holdings plc" else [one, two]

    monkeypatch.setattr(resolver, "_search", fake_search)

    with pytest.raises(GlobalProviderError, match="ambiguous/unavailable"):
        resolver.resolve_exact_legal_name("Example Holdings plc")


def test_yahoo_supplement_populates_metrics_without_clearing_evidence_gate(monkeypatch):
    provider = YahooFundamentalsProvider()
    payload = {
        "timeseries": {
            "error": None,
            "result": [
                {"annualTotalRevenue": [
                    {"asOfDate": "2025-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 1200}},
                    {"asOfDate": "2024-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 1000}},
                ]},
                {"annualNetIncome": [
                    {"asOfDate": "2025-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 120}},
                    {"asOfDate": "2024-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 80}},
                ]},
                {"annualTotalAssets": [
                    {"asOfDate": "2025-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 3000}},
                ]},
                {"annualOperatingCashFlow": [
                    {"asOfDate": "2025-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 250}},
                ]},
                {"annualFreeCashFlow": [
                    {"asOfDate": "2025-12-31", "currencyCode": "SGD", "reportedValue": {"raw": 200}},
                ]},
            ],
        }
    }
    monkeypatch.setattr(provider, "_request", lambda symbol: payload)

    company = GlobalCompany(
        country="SG",
        exchange="SGX",
        mic_code="XSES",
        currency="SGD",
        ticker="D05",
        name="DBS Group Holdings Ltd",
        price=10.0,
        price_observed_at="2026-09-17T01:00:00+00:00",
        sources=[SourceEvidence(
            provider="yahoo-public-chart-global",
            source_type="public_daily_market_history",
            source_id="D05.SI",
            quality=0.72,
        )],
    )

    enriched = provider.enrich_fundamentals(company)
    assert enriched.revenue == 1200
    assert enriched.revenue_yoy_pct == pytest.approx(20.0)
    assert enriched.net_margin_pct == pytest.approx(10.0)
    assert enriched.total_assets == 3000
    assert enriched.operating_cash_flow == 250
    assert enriched.free_cash_flow == 200
    assert any(source.source_type == "public_vendor_financial_metrics" for source in enriched.sources)

    evidence = evidence_agent(enriched)
    assert evidence.status == "BLOCK"
    assert "fundamental_source" in evidence.missing_critical
