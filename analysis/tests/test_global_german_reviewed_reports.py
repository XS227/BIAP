from __future__ import annotations

import pytest

from global_markets.german_reviewed_reports import GermanReviewedAnnualReportProvider
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError


def _mbg(*, ticker: str = "MBG", isin: str = "DE0007100000") -> GlobalCompany:
    return GlobalCompany(
        country="DE",
        exchange="XETRA",
        mic_code="XETR",
        currency="EUR",
        ticker=ticker,
        name="MERCEDES-BENZ GRP NA O.N.",
        isin=isin,
    )


def test_mercedes_reviewed_annual_report_snapshot_is_official_and_current():
    enriched = GermanReviewedAnnualReportProvider().enrich_fundamentals(_mbg())

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.revenue == 132_214_000_000
    assert enriched.revenue_prev == 145_594_000_000
    assert enriched.net_income == 5_331_000_000
    assert enriched.total_assets == 255_466_000_000
    assert enriched.total_liabilities == 161_226_000_000
    assert enriched.total_equity == 94_240_000_000
    assert enriched.retained_earnings == 77_631_000_000
    assert enriched.current_assets == 102_132_000_000
    assert enriched.current_liabilities == 73_768_000_000
    assert enriched.cash_and_equivalents == 12_254_000_000
    assert enriched.operating_cash_flow == 18_006_000_000
    assert enriched.free_cash_flow == 8_264_000_000
    assert enriched.total_debt == 100_006_000_000
    assert enriched.eps == 5.34
    assert enriched.sources[-1].provider == "de-reviewed-issuer-annual-report"
    assert enriched.sources[-1].source_type == "official_issuer_financial_statement"
    assert enriched.sources[-1].audit_status == "audited"


def test_reviewed_german_report_requires_exact_isin_and_ticker():
    provider = GermanReviewedAnnualReportProvider()
    with pytest.raises(GlobalProviderError, match="no reviewed"):
        provider.enrich_fundamentals(_mbg(isin="DE0000000001"))
    with pytest.raises(GlobalProviderError, match="ticker mismatch"):
        provider.enrich_fundamentals(_mbg(ticker="NOTMBG"))
