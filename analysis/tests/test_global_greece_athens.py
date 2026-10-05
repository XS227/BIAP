"""Greece Euronext Athens ESEF locator: ISIN -> issuer code via the official
JSON directories, annual iXBRL zips only, newest consolidated first."""
from __future__ import annotations

import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import GreeceAthensLocator, NationalOAMESEFProvider, OAMHttp
from global_markets.providers import GlobalProviderError

STOCKS = {"data": [{"Symbol": "ETE", "Issuer": "NAT. BANK OF GREECE SA", "_issuerFullName": "NATIONAL BANK OF GREECE S.A.", "ISIN": "GRS003003035"}]}
ISSUERS = {"data": [{"Code": "57", "Name": "NAT.  BANK OF GREECE SA", "Status": "ASE"}]}
PAGE = """<table><tr><th>Title</th></tr>
<tr><td>Financial report NBG (2026,Six-Month Statement,Consolidated)-iXBRL</td><td>30-09-2026 10:00</td>
<td><a href="https://athens.euronext.com/sites/default/files/hermes_3/2026-09/en/x/hy.zip">ZIP</a></td></tr>
<tr><td>Financial report NBG (2025,Annual report,Consolidated)-iXBRL</td><td>12-03-2026 09:37</td>
<td><a href="https://athens.euronext.com/sites/default/files/hermes_3/2026-03/en/y/fy2025.zip">ZIP</a></td></tr>
<tr><td>Financial Report NBG (2024,Year Statement,Both)-iXBRL.zip</td><td>17-03-2025 20:12</td>
<td><a href="/en/documents/10180/6234395/fy2024-iXBRL.zip/56e5944d-a711-4d53-9162-c082cfca6dcd">ZIP</a></td></tr>
</table>"""


class _Locator(GreeceAthensLocator):
    def __init__(self):
        super().__init__(OAMHttp())
        texts = {"athens-stocks": json.dumps(STOCKS), "athens-issuers": json.dumps(ISSUERS), "athens-esef:57": PAGE}
        self.http.cached_text = lambda key, fetch: texts[key]  # type: ignore[method-assign]


COMPANY = GlobalCompany(country="GR", exchange="ATHENS", currency="EUR", ticker="ETE", name="NBG", isin="GRS003003035")


def test_isin_to_issuer_code_and_annual_zips_only():
    filings = _Locator().annual_filings(COMPANY, "5UMCZOEYKCVFAW8ZLO05", "NATIONAL BANK OF GREECE")
    assert [f.published_at for f in filings] == ["2026-03-12", "2025-03-17"]
    assert filings[0].package_url.endswith("/fy2025.zip") and filings[0].scope == "consolidated"
    assert filings[1].package_url.startswith("https://athens.euronext.com/en/documents/10180/")


def test_unknown_isin_is_not_guessed():
    with pytest.raises(GlobalProviderError, match="no unique row"):
        _Locator().annual_filings(GlobalCompany(country="GR", exchange="ATHENS", currency="EUR", ticker="X", name="X", isin="GRS999999999"), "L", "X")


def test_greece_is_served_by_national_oam_provider():
    assert NationalOAMESEFProvider().supports("GR")
