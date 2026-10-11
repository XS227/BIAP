from __future__ import annotations

import copy

import pytest

from global_markets.evidence_contract import is_official_fundamental_source
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.us_reviewed_reports import USReviewedSECAnnualReportProvider, pinned_document_sha256


def _us(ticker: str, name: str, *, exchange: str = "NYSE", cik: int | None = None) -> GlobalCompany:
    return GlobalCompany(
        country="US",
        exchange=exchange,
        currency="USD",
        ticker=ticker,
        name=name,
        raw_provider_fields={"sec_cik": cik} if cik is not None else {},
    )


def test_gam_ncsr_annual_report_is_official_and_balances():
    enriched = USReviewedSECAnnualReportProvider().enrich_fundamentals(
        _us("GAM", "General American Investors Company, Inc. Common Stock")
    )

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.reporting_currency == "USD"
    assert enriched.revenue == 24_306_604
    assert enriched.total_assets == 1_773_357_244
    # Statement total liabilities 17,214,488 + preferred at liquidation value 190,038,825.
    assert enriched.total_liabilities == 207_253_313
    assert enriched.total_equity == 1_566_103_931
    assert enriched.raw_provider_fields["sec_cik"] == 40417
    assert enriched.raw_provider_fields["sec_form"] == "N-CSR"
    source = enriched.sources[-1]
    assert source.provider == "us-reviewed-sec-edgar-annual-report"
    assert source.source_url.startswith("https://www.sec.gov/Archives/edgar/data/40417/000199937126003330/")
    assert source.audit_status == "audited"
    assert is_official_fundamental_source(source)


def test_gab_debt_is_mandatorily_redeemable_preferred_only():
    enriched = USReviewedSECAnnualReportProvider().enrich_fundamentals(
        _us("GAB", "Gabelli Equity Trust, Inc. (The) Common Stock")
    )

    # Series M 68,550,000 + Series Q 34,040,000 classified as liabilities.
    assert enriched.total_debt == 102_590_000
    assert enriched.total_assets - enriched.total_liabilities == enriched.total_equity


def test_reviewed_sec_report_requires_matching_listing_and_cik():
    provider = USReviewedSECAnnualReportProvider()
    with pytest.raises(GlobalProviderError, match="no reviewed SEC EDGAR"):
        provider.enrich_fundamentals(_us("GAM", "General American Investors", exchange="NASDAQ"))
    with pytest.raises(GlobalProviderError, match="issuer mismatch"):
        provider.enrich_fundamentals(_us("GAM", "Gamma Holdings Inc."))
    with pytest.raises(GlobalProviderError, match="CIK mismatch"):
        provider.enrich_fundamentals(_us("GAM", "General American Investors Company, Inc.", cik=1))
    with pytest.raises(GlobalProviderError, match="US listings only"):
        provider.enrich_fundamentals(GlobalCompany(
            country="CA", exchange="TSX", currency="CAD", ticker="GAM", name="GAM",
        ))


def _row(**overrides) -> dict:
    row = copy.deepcopy(USReviewedSECAnnualReportProvider.load_registry()["NYSE:GAM"])
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sourceUrl": "https://www.sec.gov/Archives/edgar/data/1/000199937126003330/x.htm"}, "not the EDGAR document"),
        ({"sourceUrl": "http://www.sec.gov/Archives/edgar/data/40417/000199937126003330/x.htm"}, "not the EDGAR document"),
        ({"form": "N-CSRS"}, "not an annual report"),
        ({"accession": "1999371-26-3330"}, "invalid accession"),
        ({"secEntityName": "OTHER FUND INC"}, "does not match"),
        ({"sha256": ""}, "SHA-256"),
    ],
)
def test_registry_rows_fail_closed_on_provenance(overrides, message):
    with pytest.raises(ValueError, match=message):
        USReviewedSECAnnualReportProvider({"NYSE:GAM": _row(**overrides)})


def test_pin_ignores_akamai_injections_but_not_filing_text():
    body = b"<html><head><title>N-CSR</title></head><body>Net assets 1,566,103,931</body>\n</html>\n"
    sensor = b'<script type="text/javascript"  src="/LsEXsLQkpInDfWOc80pW8f_lmDc/3bb3JX0JLfLmXh/Tis/eAgbG/kUOCEc"></script>'
    rotated = b'<script type="text/javascript"  src="/Zq9yQ/aB12-cd_ef/Gh"></script>'
    beacon = (
        b'<script >bazadebezolkohpepadr="361857707"</script>'
        b'<script type="text/javascript" src="https://www.sec.gov/akam/13/159181b4"  defer></script>'
    )
    pixel = b'<noscript><img src="https://www.sec.gov/akam/13/pixel_159181b4?a=dD1h" style="visibility: hidden;" /></noscript>'

    clean = body.replace(b"</body>", sensor + b"</body>")
    rotated_sensor = body.replace(b"</body>", rotated + b"</body>")
    flagged = body.replace(b"</head>", beacon + b"</head>").replace(b"</body>", sensor + pixel + b"</body>")
    edited = clean.replace(b"1,566,103,931", b"1,566,103,932")

    assert pinned_document_sha256(clean) == pinned_document_sha256(body)
    assert pinned_document_sha256(rotated_sensor) == pinned_document_sha256(body)
    assert pinned_document_sha256(flagged) == pinned_document_sha256(body)
    assert pinned_document_sha256(edited) != pinned_document_sha256(body)
