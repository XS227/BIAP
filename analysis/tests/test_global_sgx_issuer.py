from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.sgx_issuer import SGXIssuerFundamentalsProvider


def _company(ticker: str = "S68", name: str = "Singapore Exchange Limited") -> GlobalCompany:
    return GlobalCompany(
        country="SG",
        exchange="SGX",
        mic_code="XSES",
        currency="SGD",
        ticker=ticker,
        name=name,
    )


def test_s68_official_issuer_financial_information_is_parsed(monkeypatch):
    provider = SGXIssuerFundamentalsProvider()
    text = """
    Financial Information
    S$M unless otherwise stated FY22 FY23 FY24 FY25 FY26
    Operating revenue 1,099 1,194 1,232 1,371 1,559
    Net revenue 1,030 1,121 1,162 1,298 1,478
    EBITDA 634 688 702 828 969
    EBITDA margin (%) 62 61 60 64 66
    Operating profit 537 590 606 743 887
    Operating profit margin (%) 52 53 52 57 60
    Adjusted net profit attributable to equity holders of the company 456 503 526 610 759
    """
    monkeypatch.setattr(provider, "_get_text", lambda: " ".join(text.split()))

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.revenue == 1_559_000_000
    assert enriched.revenue_prev == 1_371_000_000
    assert round(enriched.revenue_yoy_pct, 2) == 13.71
    assert enriched.ebitda == 969_000_000
    assert enriched.operating_income == 887_000_000
    assert enriched.net_income is None
    assert enriched.reporting_currency == "SGD"
    assert enriched.filing_period_end == "2026-06-30"
    assert enriched.sources[-1].provider == provider.provider_id
    assert enriched.sources[-1].source_type == "official_issuer_fundamentals"


def test_sgx_issuer_adapter_rejects_other_tickers():
    provider = SGXIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="no verified SG issuer parser"):
        provider.enrich_fundamentals(_company("D05", "DBS Group Holdings Ltd"))


def test_sgx_issuer_adapter_rejects_s68_name_collision():
    provider = SGXIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="identity mismatch"):
        provider.enrich_fundamentals(_company("S68", "Some Other Limited"))
