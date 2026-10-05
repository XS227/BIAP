"""Belgium FSMA STORI locator: ISIN-filtered annual reports, newest first,
package preferred over bare xhtml, English preferred."""
from __future__ import annotations

import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import BelgiumSTORILocator, NationalOAMESEFProvider, OAMHttp
from global_markets.providers import GlobalProviderError

ITEMS = {"storiResultItems": [
    {"companyName": "JENSEN GROUP", "reportingTopicName": "Annual financial report", "datePublication": "2025-03-28T10:34:00",
     "mainDocuments": [{"fileDataId": "old-en-zip", "language": "en", "fileType": "zip", "originalFileName": "x-2024-12-31-0-en.zip"}]},
    {"companyName": "JENSEN GROUP", "reportingTopicName": "Annual financial report", "datePublication": "2026-03-27T08:00:00",
     "mainDocuments": [
         {"fileDataId": "nl-xhtml", "language": "nl", "fileType": "xhtml", "originalFileName": "x-2025-12-31-0-nl.xhtml"},
         {"fileDataId": "en-xhtml", "language": "en", "fileType": "xhtml", "originalFileName": "x-2025-12-31-0-en.xhtml"},
         {"fileDataId": "nl-zip", "language": "nl", "fileType": "zip", "originalFileName": "x-2025-12-31-0-nl.zip"},
         {"fileDataId": "en-zip", "language": "en", "fileType": "zip", "originalFileName": "x-2025-12-31-0-en.zip"}]},
    {"companyName": "JENSEN GROUP", "reportingTopicName": "Annual financial report", "datePublication": "2011-03-28T08:30:00",
     "mainDocuments": [{"fileDataId": "pdf", "language": "en", "fileType": "pdf", "originalFileName": "AR 2010.pdf"}]},
]}


class _Locator(BelgiumSTORILocator):
    def __init__(self, payload=ITEMS):
        super().__init__(OAMHttp())
        self.http.cached_text = lambda key, fetch: json.dumps(payload)  # type: ignore[method-assign]


COMPANY = GlobalCompany(country="BE", exchange="EURONEXT_BRUSSELS", currency="EUR", ticker="JEN", name="JENSEN", isin="BE0003858751")


def test_newest_first_package_and_english_preferred():
    filings = _Locator().annual_filings(COMPANY, "549300VL91FV2CP8L882", "JENSEN-GROUP")
    assert [f.document_id for f in filings] == ["FSMA-STORI:en-zip", "FSMA-STORI:old-en-zip"]
    assert filings[0].package_url.endswith("/download?fileDataId=en-zip")
    assert filings[0].published_at == "2026-03-27"


def test_requires_isin_and_esef_lodgement():
    with pytest.raises(GlobalProviderError, match="requires the instrument ISIN"):
        _Locator().annual_filings(GlobalCompany(country="BE", exchange="X", currency="EUR", ticker="JEN", name="J"), "L", "J")
    with pytest.raises(GlobalProviderError, match="no ESEF annual financial report"):
        _Locator({"storiResultItems": ITEMS["storiResultItems"][2:]}).annual_filings(COMPANY, "L", "J")


def test_belgium_is_served_by_national_oam_provider():
    assert NationalOAMESEFProvider().supports("BE")


def test_cross_listed_foreign_issuer_uses_home_state_oam():
    provider = NationalOAMESEFProvider()
    athens_listed_belgian = GlobalCompany(country="GR", exchange="ATHENS", currency="EUR", ticker="VIO",
                                          name="VIOHALCO", isin="BE0974271034")
    assert isinstance(provider.locator_for(athens_listed_belgian), BelgiumSTORILocator)
    luxembourg = GlobalCompany(country="NL", exchange="EURONEXT_AMSTERDAM", currency="EUR", ticker="MT",
                               name="ARCELORMITTAL", isin="LU1598757687")
    # No Luxembourg locator: the listing country's OAM is used.
    assert provider.locator_for(luxembourg).country == "NL"
