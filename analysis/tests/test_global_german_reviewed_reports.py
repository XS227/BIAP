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


@pytest.mark.parametrize(
    ("ticker", "isin", "period", "revenue", "assets", "current_assets", "current_liabilities"),
    [
        ("SHL", "DE000SHL1006", "2025-09-30", 23_375_000_000, 44_370_000_000, 14_098_000_000, 12_644_000_000),
        ("KBX", "DE000KBX1006", "2025-12-31", 7_817_000_000, 8_883_000_000, 4_897_000_000, 2_622_000_000),
        ("BEZ", "DE0005201602", "2025-12-31", 162_900_000, 129_752_000, 74_171_000, 73_636_000),
    ],
)
def test_reviewed_report_registry_covers_remaining_regulated_canaries(
    ticker, isin, period, revenue, assets, current_assets, current_liabilities
):
    provider = GermanReviewedAnnualReportProvider()
    company = GlobalCompany(
        country="DE",
        exchange="XETRA",
        mic_code="XETR",
        currency="EUR",
        ticker=ticker,
        name=ticker,
        isin=isin,
    )

    enriched = provider.enrich_fundamentals(company)

    assert enriched.filing_period_end == period
    assert enriched.revenue == revenue
    assert enriched.total_assets == assets
    assert enriched.current_assets == current_assets
    assert enriched.current_liabilities == current_liabilities
    assert enriched.sources[-1].provider == "de-reviewed-issuer-annual-report"
    assert enriched.sources[-1].audit_status == "audited"


@pytest.mark.parametrize(
    ("ticker", "isin", "expected_sector", "expected_assets"),
    [
        ("MUX", "DE000A2NB650", "Industrials", 5_184_200_000),
        ("UBK", "DE0005570808", "Banking", 7_030_980_000),
        ("BENH", "DE000A11QLP3", "Real Estate", 99_396_000),
    ],
)
def test_mux_umweltbank_beno_reviewed_reports(ticker, isin, expected_sector, expected_assets):
    provider = GermanReviewedAnnualReportProvider()
    company = GlobalCompany(
        country="DE",
        exchange="FRANKFURT",
        mic_code="XFRA",
        currency="EUR",
        ticker=ticker,
        name=ticker,
        isin=isin,
    )

    enriched = provider.enrich_fundamentals(company)

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.total_assets == expected_assets
    assert enriched.sector == expected_sector
    assert enriched.sources[-1].provider == "de-reviewed-issuer-annual-report"
    assert enriched.sources[-1].audit_status == "audited"
    assert enriched.audit_opinion == "unqualified"

    if ticker == "MUX":
        assert enriched.ebitda == 675_300_000
        assert enriched.current_assets == 2_914_700_000
        assert enriched.current_liabilities == 3_325_200_000
        assert enriched.total_debt == 1_654_900_000
    elif ticker == "UBK":
        assert enriched.industry == "Bank"
        assert enriched.net_income == 12_264_000
    elif ticker == "BENH":
        assert enriched.operating_income == 6_542_000
        assert enriched.raw_provider_fields["agent10_ffo"] == 2_246_000
        assert enriched.total_debt == 56_008_000
