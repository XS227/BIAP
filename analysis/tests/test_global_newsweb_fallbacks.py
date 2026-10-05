"""Newsweb: share-class ticker -> issuer sign, and LEI-named ESEF packages
filed outside the annual-report category."""
from __future__ import annotations

from global_markets.models import GlobalCompany
from global_markets.oam_esef import NorwayNewswebLocator, OAMHttp

LEI = "549300CVBE06T0SH6T76"


class _Locator(NorwayNewswebLocator):
    def __init__(self, lists, details):
        super().__init__(OAMHttp())
        self.lists, self.details = lists, details

    def _json(self, path, params):
        if path == "list":
            return {"messages": self.lists.get((params["issuer"], params.get("category")), [])}
        return {"message": self.details[params["messageId"]]}


def test_share_class_ticker_falls_back_to_issuer_sign():
    assert NorwayNewswebLocator._signs(GlobalCompany(country="NO", exchange="X", currency="NOK", ticker="ODFB", name="O")) == ["ODFB", "ODF"]
    assert NorwayNewswebLocator._signs(GlobalCompany(country="NO", exchange="X", currency="NOK", ticker="DNB", name="D")) == ["DNB"]


def test_lei_named_package_outside_annual_category_is_found_but_others_ignored():
    press = {"messageId": 2, "issuerSign": "ELK", "title": "Elkem ASA - Integrated annual report for 2025", "publishedTime": "2026-03-19"}
    lists = {("ELK", 1001): [], ("ELK", None): [press]}
    details = {2: {"publishedTime": "2026-03-19", "title": press["title"], "attachments": [
        {"id": 7, "name": f"{LEI}_2025_12_31_1_en.zip"},
        {"id": 8, "name": "presentation.zip"},
    ]}}
    company = GlobalCompany(country="NO", exchange="EURONEXT_OSLO", currency="NOK", ticker="ELK", name="ELKEM")
    filings = _Locator(lists, details).annual_filings(company, LEI, "ELKEM ASA")
    assert [f.document_id for f in filings] == ["NEWSWEB:2:7"]
