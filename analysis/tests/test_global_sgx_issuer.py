from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.sgx_issuer import SGXIssuerFundamentalsProvider, parse_sgx_fy2026_results


def _company(ticker: str = "S68", name: str = "Singapore Exchange Limited") -> GlobalCompany:
    return GlobalCompany(
        country="SG",
        exchange="SGX",
        mic_code="XSES",
        currency="SGD",
        ticker=ticker,
        name=name,
    )


FY2026_RESULTS = """
FY2026 SGX Group Financial Results
SGX recorded EBITDA of $969.3 million ($827.8 million) and NPAT of
$698.4 million ($648.0 million) in FY2026. EPS was 65.3 cents (60.6 cents).
Operating revenue increased $188.8 million or 13.8% to $1,559.5 million
($1,370.6 million). After netting off transaction-based expenses, net revenue
increased to $1,478.3 million.
"""


def test_parse_sgx_fy2026_statutory_headline_results():
    metrics = parse_sgx_fy2026_results(FY2026_RESULTS)

    assert metrics["revenue"] == 1_559_500_000
    assert metrics["revenue_prev"] == 1_370_600_000
    assert round(metrics["revenue_yoy_pct"], 2) == 13.78
    assert metrics["ebitda"] == 969_300_000
    assert metrics["net_income"] == 698_400_000
    assert round(metrics["net_margin_pct"], 2) == 44.78
    assert metrics["eps"] == 0.653


def test_s68_official_issuer_results_are_applied(monkeypatch):
    provider = SGXIssuerFundamentalsProvider()
    monkeypatch.setattr(provider, "_get_text", lambda: FY2026_RESULTS)

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.revenue == 1_559_500_000
    assert enriched.net_income == 698_400_000
    assert enriched.eps == 0.653
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
