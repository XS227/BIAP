from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from global_markets.evidence_contract import is_official_fundamental_source
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.providers import FundamentalsProvider, GlobalProviderError
from global_markets.uk_reviewed_reports import UKReviewedNSMAnnualReportProvider, _registry


def _gb(ticker: str, isin: str, *, lei: str | None = None) -> GlobalCompany:
    return GlobalCompany(
        country="GB",
        exchange="LSE",
        mic_code="XLON",
        currency="GBP",
        ticker=ticker,
        name=ticker,
        isin=isin,
        lei=lei,
    )


def test_aberforth_untagged_nsm_annual_report_is_official_and_current():
    enriched = UKReviewedNSMAnnualReportProvider().enrich_fundamentals(_gb("ASL", "GB0000066554"))

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.reporting_currency == "GBP"
    assert enriched.revenue == 59_399_000
    assert enriched.revenue_prev == 54_624_000
    assert enriched.net_income == 96_235_000
    assert enriched.total_assets == 1_467_022_000
    assert enriched.total_liabilities == 75_306_000
    assert enriched.total_equity == 1_391_716_000
    assert enriched.total_debt == 74_973_000
    assert enriched.eps == 1.179
    assert enriched.audit_opinion == "unqualified"
    assert enriched.lei == "213800GZ9WC73A92Q326"
    source = enriched.sources[-1]
    assert source.provider == "gb-reviewed-fca-nsm-annual-report"
    assert source.source_type == "official_regulatory_filing"
    assert source.source_url.startswith("https://data.fca.org.uk/artefacts/NSM/")
    assert source.period_end == "2025-12-31"
    assert source.audit_status == "audited"
    assert is_official_fundamental_source(source)


@pytest.mark.parametrize(
    ("ticker", "isin", "period", "assets", "equity", "opinion_token"),
    [
        ("BRSC", "GB00BWQGKH23", "2026-02-28", 681_320_000, 603_842_000, "unqualified"),
        ("GSC", "GB00BP38X172", "2025-06-30", 570_063, -570_339, "going concern"),
        ("GCG", "JE00BYZT0R68", "2025-12-31", 280_109, 72_181, "qualified"),
    ],
)
def test_reviewed_nsm_registry_covers_untagged_and_rns_only_issuers(
    ticker, isin, period, assets, equity, opinion_token
):
    enriched = UKReviewedNSMAnnualReportProvider().enrich_fundamentals(_gb(ticker, isin))

    assert enriched.filing_period_end == period
    assert enriched.total_assets == assets
    assert enriched.total_equity == equity
    assert opinion_token in enriched.audit_opinion
    assert enriched.sources[-1].provider == "gb-reviewed-fca-nsm-annual-report"


def test_reviewed_nsm_report_requires_exact_isin_ticker_and_lei():
    provider = UKReviewedNSMAnnualReportProvider()
    with pytest.raises(GlobalProviderError, match="no reviewed"):
        provider.enrich_fundamentals(_gb("ASL", "GB0000000001"))
    with pytest.raises(GlobalProviderError, match="ticker mismatch"):
        provider.enrich_fundamentals(_gb("NOTASL", "GB0000066554"))
    with pytest.raises(GlobalProviderError, match="LEI mismatch"):
        provider.enrich_fundamentals(_gb("ASL", "GB0000066554", lei="5493000000000000XX00"))
    with pytest.raises(GlobalProviderError, match="GB listings only"):
        provider.enrich_fundamentals(GlobalCompany(
            country="IE", exchange="EURONEXT_DUBLIN", currency="EUR",
            ticker="ASL", name="ASL", isin="GB0000066554",
        ))


def _row(**overrides) -> dict:
    row = copy.deepcopy(_registry()["GB0000066554"])
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sourceUrl": "https://www.aberforth.co.uk/report.pdf"}, "not an FCA NSM artefact"),
        ({"sourceUrl": "http://data.fca.org.uk/artefacts/NSM/x.html"}, "not an FCA NSM artefact"),
        ({"sha256": ""}, "SHA-256"),
        ({"periodEnd": "FY2025"}, "invalid periodEnd"),
    ],
)
def test_registry_rows_fail_closed_on_provenance(overrides, message):
    with pytest.raises(ValueError, match=message):
        UKReviewedNSMAnnualReportProvider({"GB0000066554": _row(**overrides)})


def test_registry_rejects_adverse_opinion_and_broken_balance_sheet():
    adverse = _row()
    adverse["fundamentals"] = {**adverse["fundamentals"], "audit_opinion": "adverse (going concern basis inappropriate)"}
    with pytest.raises(ValueError, match="adverse"):
        UKReviewedNSMAnnualReportProvider({"GB0000066554": adverse})

    broken = _row()
    broken["fundamentals"] = {**broken["fundamentals"], "total_equity": 1_000}
    with pytest.raises(ValueError, match="assets - liabilities = equity"):
        UKReviewedNSMAnnualReportProvider({"GB0000066554": broken})


def test_every_shipped_registry_row_balances():
    for isin, row in _registry().items():
        values = row["fundamentals"]
        assert values["total_assets"] - values["total_liabilities"] == values["total_equity"], isin


class _TaggedNSM(FundamentalsProvider):
    provider_id = "tagged-nsm"

    def __init__(self, period: str | None) -> None:
        self.period = period

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if self.period is None:
            raise GlobalProviderError("FCA NSM annual financial reports are lodged untagged")
        return replace(company, filing_period_end=self.period, revenue=1.0)


def test_tagged_nsm_filing_wins_over_reviewed_snapshot_when_current():
    chain = FallbackFundamentalsProvider(_TaggedNSM("2026-12-31"), UKReviewedNSMAnnualReportProvider())
    enriched = chain.enrich_fundamentals(_gb("ASL", "GB0000066554"))
    assert enriched.filing_period_end == "2026-12-31"
    assert not any(s.provider == "gb-reviewed-fca-nsm-annual-report" for s in enriched.sources)


def test_reviewed_snapshot_fills_untagged_or_stale_tagged_chain():
    untagged = FallbackFundamentalsProvider(_TaggedNSM(None), UKReviewedNSMAnnualReportProvider())
    enriched = untagged.enrich_fundamentals(_gb("ASL", "GB0000066554"))
    assert enriched.filing_period_end == "2025-12-31"
    assert "untagged" in enriched.raw_provider_fields["fundamentals_primary_error"]

    stale = FallbackFundamentalsProvider(_TaggedNSM("2024-12-31"), UKReviewedNSMAnnualReportProvider())
    enriched = stale.enrich_fundamentals(_gb("GCG", "JE00BYZT0R68"))
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.raw_provider_fields["fundamentals_fallback_reason"] == "newer_period_available"


def test_pin_ignores_only_cloudflare_email_obfuscation():
    from global_markets.uk_reviewed_reports import pinned_document_sha256

    a = b'<a href="/cdn-cgi/l/email-protection#4f232a"><span data-cfemail="6d0108">x</span></a> Loss (215,963)'
    b = b'<a href="/cdn-cgi/l/email-protection#d1bdb4"><span data-cfemail="acc0c9">x</span></a> Loss (215,963)'
    c = b'<a href="/cdn-cgi/l/email-protection#d1bdb4"><span data-cfemail="acc0c9">x</span></a> Loss (215,964)'
    assert pinned_document_sha256(a) == pinned_document_sha256(b)
    assert pinned_document_sha256(a) != pinned_document_sha256(c)
