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
