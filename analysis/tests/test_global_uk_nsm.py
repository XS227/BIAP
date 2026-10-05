"""UK FCA NSM locator: LEI-checked tagged annual reports and rate-block cooldown."""
from __future__ import annotations

import json
import time

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import NationalOAMESEFProvider, OAMHttp, UKNSMLocator
from global_markets.providers import GlobalProviderError

LEI = "2138002P5RNKC5W2JZ46"


def _hit(lei, kind, link, date, ident):
    return {"_source": {"lei": lei, "type": kind, "download_link": link, "publication_date": date,
                        "disclosure_id": ident, "company": "TESCO PLC", "headline": "Annual Financial Report"}}


HITS = {"hits": {"hits": [
    _hit(LEI, "Annual Financial Report", "NSM/Portal/NI-1/NI-1_x-2025-02-22.zip", "2025-05-08T00:00:00Z", "NI-1"),
    _hit(LEI, "Annual Financial Report", "NSM/DirectUpload/NI-2/NI-2_x-2026-02-28.zip", "2026-05-14T00:00:00Z", "NI-2"),
    _hit("213800OTHERLEI000000", "Annual Financial Report", "NSM/x/other.zip", "2026-06-01T00:00:00Z", "NI-3"),
    _hit(LEI, "Half-year Report", "NSM/x/hy.zip", "2026-09-01T00:00:00Z", "NI-4"),
    _hit(LEI, "Annual Financial Report", "NSM/x/report.pdf", "2026-05-14T00:00:00Z", "NI-5"),
]}}

COMPANY = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="TSCO", name="TESCO", isin="GB00BLGZ9862")


class _Locator(UKNSMLocator):
    def __init__(self, payload=HITS):
        super().__init__(OAMHttp())
        self.http.cached_text = lambda key, fetch: json.dumps(payload)  # type: ignore[method-assign]


def test_only_own_lei_tagged_annual_packages_newest_first():
    filings = _Locator().annual_filings(COMPANY, LEI.lower(), "TESCO PLC")
    assert [f.document_id for f in filings] == ["FCA-NSM:NI-2", "FCA-NSM:NI-1"]
    assert filings[0].package_url == "https://data.fca.org.uk/artefacts/NSM/DirectUpload/NI-2/NI-2_x-2026-02-28.zip"


def test_no_esef_report_is_explicit():
    with pytest.raises(GlobalProviderError, match="no tagged ESEF annual financial report"):
        _Locator({"hits": {"hits": []}}).annual_filings(COMPANY, LEI, "TESCO PLC")


def test_cooldown_blocks_calls_after_rate_block(monkeypatch):
    monkeypatch.setattr(UKNSMLocator, "_blocked_until", time.monotonic() + 60)
    with pytest.raises(GlobalProviderError, match="cooling down"):
        UKNSMLocator(OAMHttp())._throttle()
    monkeypatch.setattr(UKNSMLocator, "_blocked_until", 0.0)


def test_gb_is_served_by_national_oam_provider():
    assert NationalOAMESEFProvider().supports("GB")
