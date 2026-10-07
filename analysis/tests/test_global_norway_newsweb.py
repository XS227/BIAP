from global_markets.models import GlobalCompany
from global_markets.oam_esef import NorwayNewswebLocator


class _FakeHTTP:
    pass


def test_newsweb_accepts_xbri_esef_attachment(monkeypatch):
    locator = NorwayNewswebLocator(_FakeHTTP())
    company = GlobalCompany(country="NO", exchange="EURONEXT_OSLO", ticker="NEXT", name="NEXT Biometrics Group ASA", currency="NOK", isin="NO0013740142", lei="5967007LIEEXZXK9R405")

    def fake_json(path, params):
        if path == "list":
            return {"messages": [{"issuerSign": "NEXT", "messageId": 671621, "publishedTime": "2026-04-28T09:10:00Z", "title": "NEXT Biometrics Group ASA: Annual Report 2025"}]}
        return {"message": {"publishedTime": "2026-04-28T09:10:00Z", "title": "Annual Report 2025", "attachments": [{"id": 324189, "name": "NB_Group_ASA_Annual_report_2025-12-31.xbri"}, {"id": 324190, "name": "NEXT Biometrics Annual Report 2025.pdf"}]}}

    monkeypatch.setattr(locator, "_json", fake_json)
    filings = locator.annual_filings(company, company.lei, company.name)
    assert len(filings) == 1
    assert filings[0].document_id == "NEWSWEB:671621:324189"
    assert "attachmentId=324189" in filings[0].package_url
