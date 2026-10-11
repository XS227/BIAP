"""Nasdaq Nordic announcements locator and the Danish combined locator."""
from __future__ import annotations

import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import (
    DenmarkCombinedLocator,
    NasdaqNordicNewsLocator,
    OAMFiling,
    OAMHttp,
)
from global_markets.providers import GlobalProviderError

ITEMS = {"results": {"item": [
    {"disclosureId": 1, "published": "2026-02-05 08:00:00", "company": "Danske Bank A/S", "cnsCategory": "Annual Financial Report",
     "headline": "Annual Report 2025", "attachment": [
         {"fileName": "DanskeBank-2025-12-31-0-en.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/a1"},
         {"fileName": "AR2025.pdf", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/a2"}]},
    {"disclosureId": 2, "published": "2026-02-05 08:00:00", "company": "Realkredit Danmark A/S", "cnsCategory": "Annual Financial Report",
     "headline": "Annual Report 2025", "attachment": [
         {"fileName": "RealkreditDanmark-2025-12-31-0-en.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/a3"}]},
    {"disclosureId": 3, "published": "2026-03-01 08:00:00", "company": "Danske Bank A/S", "cnsCategory": "Changes in company's own shares",
     "headline": "x", "attachment": [{"fileName": "x.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/a4"}]},
]}}


class _News(NasdaqNordicNewsLocator):
    def __init__(self, payload=ITEMS):
        super().__init__(OAMHttp())
        self.http.cached_text = lambda key, fetch: json.dumps(payload)  # type: ignore[method-assign]


COMPANY = GlobalCompany(country="DK", exchange="NASDAQ_COPENHAGEN", currency="DKK", ticker="DANSKE", name="DANSKE BANK")


def test_only_same_issuer_annual_report_packages():
    filings = _News().annual_filings(COMPANY, "MAES062Z21O4RZ2U7M96", "Danske Bank A/S")
    assert [f.package_url for f in filings] == ["https://attachment.news.eu.nasdaq.com/a1"]


def test_no_package_is_explicit():
    with pytest.raises(GlobalProviderError, match="no ESEF annual report"):
        _News({"results": {"item": []}}).annual_filings(COMPANY, "L", "Heimar hf.")


def test_combined_locator_merges_newest_first():
    class _A:
        def annual_filings(self, *a):
            return [OAMFiling(oam="v", document_id="virk", package_url="u1", landing_url="l", published_at="2025-04-23")]

    class _B:
        def annual_filings(self, *a):
            return [OAMFiling(oam="n", document_id="news", package_url="u2", landing_url="l", published_at="2026-02-05")]

    combined = DenmarkCombinedLocator(OAMHttp())
    combined.parts = [_A(), _B()]
    assert [f.document_id for f in combined.annual_filings(COMPANY, "L", "D")] == ["news", "virk"]


KALDALON_LEI = "254900A1SVOQEMA2WP49"
KALDALON = {"results": {"item": [
    {"disclosureId": 10, "published": "2026-03-26 09:00:00", "company": "Kaldalón hf.", "cnsCategory": "Annual Financial Report",
     "headline": "Annual and Sustainability Report 2025 Published", "attachment": []},
    {"disclosureId": 11, "published": "2026-03-04 09:00:00", "company": "Kaldalón hf.", "cnsCategory": "Financial Statement Release",
     "headline": "Financial Statements 2025", "attachment": [
         {"fileName": f"{KALDALON_LEI}-2025-12-31-1-is.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/k1"},
         {"fileName": "Kaldalon - Samstuarsreikningur 2025.pdf", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/k2"}]},
    {"disclosureId": 12, "published": "2026-08-20 09:00:00", "company": "Kaldalón hf.", "cnsCategory": "Half Year financial report",
     "headline": "Interim", "attachment": [{"fileName": "interim.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/k3"}]},
    {"disclosureId": 13, "published": "2026-03-04 09:00:00", "company": "Kaldalón hf.", "cnsCategory": "Financial Statement Release",
     "headline": "Other issuer's package", "attachment": [
         {"fileName": "549300EQF6IH6OIAYL40-2025-12-31-1-is.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/k4"}]},
    {"disclosureId": 14, "published": "2026-03-04 09:00:00", "company": "Other Company hf.", "cnsCategory": "Financial Statement Release",
     "headline": "Same LEI, different announcer", "attachment": [
         {"fileName": f"{KALDALON_LEI}-2025-12-31-1-is.zip", "attachmentUrl": "https://attachment.news.eu.nasdaq.com/k5"}]},
]}}
KALDALON_CO = GlobalCompany(country="IS", exchange="NASDAQ_ICELAND", currency="ISK", ticker="KALD", name="Kaldalón")


def test_lei_named_esef_zip_in_financial_statement_release_is_found():
    filings = _News(KALDALON).annual_filings(KALDALON_CO, KALDALON_LEI, "Kaldalón hf.")
    # Only this issuer's LEI-named package from this issuer's own announcement; interim zips,
    # other issuers' LEIs and other announcers are all rejected.
    assert [f.package_url for f in filings] == ["https://attachment.news.eu.nasdaq.com/k1"]


def test_unrelated_category_zip_without_lei_name_is_never_accepted():
    with pytest.raises(GlobalProviderError, match="no ESEF annual report"):
        _News({"results": {"item": [KALDALON["results"]["item"][2]]}}).annual_filings(KALDALON_CO, KALDALON_LEI, "Kaldalón hf.")
