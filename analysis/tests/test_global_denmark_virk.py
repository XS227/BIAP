"""Denmark virk.dk locator: CVR from GLEIF, ESEF annual report xhtml only."""
from __future__ import annotations

import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import DenmarkVirkLocator, NationalOAMESEFProvider, OAMHttp
from global_markets.providers import GlobalProviderError

LEI = "5299001O0WJQYB5GYZ19"
GLEIF = {"data": {"attributes": {"entity": {"registeredAs": "61056416", "jurisdiction": "DK"}}}}
HITS = {"hits": {"hits": [
    {"_id": "a", "_source": {"cvrNummer": 61056416, "offentliggoerelsesTidspunkt": "2026-08-21T00:00:00Z",
     "regnskab": {"regnskabsperiode": {"slutDato": "2026-06-30"}},
     "dokumenter": [{"dokumentType": "HALVAARSRAPPORT", "dokumentMimeType": "application/xhtml+xml", "dokumentUrl": "http://x/hy.xhtml"}]}},
    {"_id": "b", "_source": {"cvrNummer": 61056416, "offentliggoerelsesTidspunkt": "2026-03-19T00:00:00Z",
     "regnskab": {"regnskabsperiode": {"slutDato": "2025-12-31"}},
     "dokumenter": [{"dokumentType": "AARSRAPPORT", "dokumentMimeType": "application/xml", "dokumentUrl": "http://x/fy.xml"},
                    {"dokumentType": "AARSRAPPORT", "dokumentMimeType": "application/xhtml+xml", "dokumentUrl": "http://x/fy.xhtml"}]}},
]}}


class _Locator(DenmarkVirkLocator):
    def __init__(self, gleif=GLEIF):
        super().__init__(OAMHttp())
        texts = {f"gleif-record:{LEI}": json.dumps(gleif), "virk-regnskab:61056416": json.dumps(HITS)}
        self.http.cached_text = lambda key, fetch: texts[key]  # type: ignore[method-assign]


COMPANY = GlobalCompany(country="DK", exchange="NASDAQ_COPENHAGEN", currency="DKK", ticker="CARL.B", name="CARLSBERG")


def test_annual_report_xhtml_only():
    filings = _Locator().annual_filings(COMPANY, LEI, "CARLSBERG A/S")
    assert [f.package_url for f in filings] == ["http://x/fy.xhtml"]
    assert filings[0].published_at == "2026-03-19"


def test_non_danish_registration_is_rejected():
    faroese = {"data": {"attributes": {"entity": {"registeredAs": "1234", "jurisdiction": "FO"}}}}
    with pytest.raises(GlobalProviderError, match="no Danish CVR"):
        _Locator(faroese).annual_filings(COMPANY, LEI, "BETRI")


def test_denmark_is_served_by_national_oam_provider():
    assert NationalOAMESEFProvider().supports("DK")
