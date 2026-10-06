from __future__ import annotations

from dataclasses import replace

import pytest

from global_markets.agents import evidence_agent
from global_markets.boerse_frankfurt_fundamentals import (
    BoerseFrankfurtFundamentalsProvider,
)
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import GlobalProviderError, append_source


def _company() -> GlobalCompany:
    return GlobalCompany(
        country="DE",
        exchange="XETRA",
        mic_code="XETR",
        currency="EUR",
        ticker="TIW",
        name="TIN INN HLDG AG VNA O.N.",
        isin="DE000A40ZTT8",
        price=15.6,
        price_observed_at="2026-10-06T18:00:00+00:00",
        sources=[
            SourceEvidence(
                provider="official-deutsche-boerse-t7-universe",
                source_type="official_exchange_universe",
                source_id="XETRA:TIW",
                quality=1.0,
            ),
            SourceEvidence(
                provider="market-test",
                source_type="market_history",
                source_id="TIW",
                quality=0.9,
            ),
        ],
    )


def _payload() -> dict:
    return {
        "isin": "DE000A40ZTT8",
        "data": [
            {
                "year": 2025,
                "currencyCode": "EUR",
                "salesRevenue": 1_480_000,
                "profitGross": -800_000,
                "incomeOperating": -4_910_000,
                "incomeNet": -6_450_000,
                "assetsCurrentTotal": 2_060_000,
                "assetsTotal": 26_540_000,
                "liabilitiesCurrentTotal": 10_090_000,
                "liabilitiesLongtermTotal": 23_220_000,
                "liabilitiesTotal": 33_310_000,
                "equityTotal": -5_670_000,
                "earningsPerShareBasic": -0.32,
                "bookvaluePerShare": -0.28,
                "priceEarningsRatio": -48.75,
                "priceBookRatio": None,
                "dividendPerShare": None,
                "dividendReturnRatio": None,
                "outstandingShares": 20_050_000,
            },
            {
                "year": 2024,
                "currencyCode": "EUR",
                "salesRevenue": 7_310_000,
                "incomeNet": 8_270_000,
                "assetsTotal": 33_860_000,
                "liabilitiesTotal": 30_340_000,
                "equityTotal": 3_520_000,
            },
        ],
    }


def test_boerse_frankfurt_key_data_normalizes_tiw_without_inventing_period(monkeypatch):
    provider = BoerseFrankfurtFundamentalsProvider()
    monkeypatch.setattr(provider, "_get_json", lambda url: _payload())

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.revenue == 1_480_000
    assert enriched.revenue_prev == 7_310_000
    assert enriched.operating_income == -4_910_000
    assert enriched.net_income == -6_450_000
    assert enriched.total_assets == 26_540_000
    assert enriched.total_liabilities == 32_210_000
    assert enriched.total_equity == -5_670_000
    assert enriched.current_assets == 2_060_000
    assert enriched.current_liabilities == 10_090_000
    assert enriched.eps == -0.32
    assert enriched.filing_period_end is None
    assert enriched.raw_provider_fields["de_bf_report_year"] == 2025
    assert enriched.raw_provider_fields["de_bf_liabilities_reported"] == 33_310_000
    assert enriched.raw_provider_fields["de_bf_liabilities_normalized_by_identity"] is True
    assert enriched.raw_provider_fields["de_bf_period_granularity"] == "year_only"

    source = enriched.sources[-1]
    assert source.provider == provider.provider_id
    assert source.source_type == "official_exchange_fundamental_metrics"
    assert source.audit_status == "unknown"
    assert source.period_end is None


def test_exchange_key_data_clears_false_source_block_with_current_year_only_official_data(monkeypatch):
    provider = BoerseFrankfurtFundamentalsProvider()
    monkeypatch.setattr(provider, "_get_json", lambda url: _payload())

    enriched = provider.enrich_fundamentals(_company())
    assessment = evidence_agent(enriched)

    assert "fundamental_source" not in assessment.missing_critical
    assert assessment.status == "PASS"
    assert assessment.freshness_score == pytest.approx(0.25)


def test_boerse_frankfurt_normalizes_liabilities_from_assets_and_equity(monkeypatch):
    payload = _payload()
    payload["data"][0] = {
        **payload["data"][0],
        "assetsTotal": 100_000_000,
        "liabilitiesTotal": 20_000_000,
        "equityTotal": 10_000_000,
    }
    provider = BoerseFrankfurtFundamentalsProvider()
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.total_liabilities == 90_000_000
    assert enriched.raw_provider_fields["de_bf_liabilities_reported"] == 20_000_000


def test_boerse_frankfurt_rejects_stale_annual_year(monkeypatch):
    payload = _payload()
    payload["data"] = [
        {**payload["data"][0], "year": 2024},
        {**payload["data"][1], "year": 2023},
    ]
    provider = BoerseFrankfurtFundamentalsProvider()
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    with pytest.raises(GlobalProviderError, match="too old"):
        provider.enrich_fundamentals(_company())
