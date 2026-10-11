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


# --- AAB (AaB A/S): virk.dk reports identify the entity by CVR, not LEI -------

AAB_LEI = "213800V1SZZTH8PC1L04"
AAB_CVR_ID = "http://www.dcca.dk/cvr|10998530"
_AAB_IXBRL = """<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"><body>
<ix:header><ix:resources>
<xbrli:context id="d"><xbrli:entity><xbrli:identifier scheme="http://www.dcca.dk/cvr">{cvr}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="dkk"><xbrli:measure>iso4217:DKK</xbrli:measure></xbrli:unit>
</ix:resources></ix:header>
<ix:nonFraction name="ifrs-full:Revenue" contextRef="d" unitRef="dkk" decimals="-3">73,785</ix:nonFraction>
</body></html>"""


def test_ixbrl_reports_context_identifiers_besides_lei():
    from global_markets.ixbrl import extract_facts, extract_facts_and_identifiers

    html = _AAB_IXBRL.format(cvr="10998530")
    facts, leis, identifiers = extract_facts_and_identifiers([html])
    assert leis == set()
    assert identifiers == {AAB_CVR_ID}
    assert len(facts) == 1
    # Legacy two-value API is unchanged.
    assert extract_facts([html])[1] == set()


def _aab_provider(monkeypatch, package_entities, package_identifiers, gleif_cvr="10998530"):
    from global_markets.oam_esef import OAMFiling

    gleif = {"data": {"attributes": {"entity": {"registeredAs": gleif_cvr, "jurisdiction": "DK"}}}}
    filing = OAMFiling(oam="dk-virk-regnskab", document_id="VIRK:10998530:2025-12-31:x", package_url="http://x/aab.xhtml",
                       landing_url="http://x", published_at="2026-05-05", scope="consolidated")
    provider = NationalOAMESEFProvider()
    locator = provider.locators["DK"]
    monkeypatch.setattr(OAMHttp, "cached_text", lambda self, key, fetch: json.dumps(gleif))
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (AAB_LEI, "AALBORG BOLDSPILKLUB A/S"))
    monkeypatch.setattr(locator, "annual_filings", lambda company, lei, name: [filing])

    def facts(concept, value, period, unit="DKK"):
        return {"value": str(value), "decimals": "-3",
                "dimensions": {"concept": concept, "entity": "x", "period": period, "unit": unit}}

    duration = "2025-01-01/2025-12-31"
    package = {"entities": package_entities, "identifiers": package_identifiers, "reportFile": "aab.xhtml",
               "facts": [facts("ifrs-full:Revenue", 73_785_000, duration), facts("ifrs-full:ProfitLoss", 6_023_000, duration),
                         facts("ifrs-full:Assets", 122_141_000, "2025-12-31"), facts("ifrs-full:Liabilities", 59_398_000, "2025-12-31"),
                         facts("ifrs-full:Equity", 62_743_000, "2025-12-31")]}
    monkeypatch.setattr(provider, "package_facts", lambda filing: package)
    return provider


AAB_COMPANY = GlobalCompany(country="DK", exchange="NASDAQ_COPENHAGEN", currency="DKK", ticker="AAB", name="AaB")


def test_aab_cvr_only_report_verified_through_gleif_registry_link(monkeypatch):
    result = _aab_provider(monkeypatch, [], [AAB_CVR_ID]).enrich_fundamentals(AAB_COMPANY)
    assert (result.revenue, result.net_income) == (73_785_000, 6_023_000)
    assert result.total_assets - result.total_liabilities == result.total_equity
    assert result.raw_provider_fields["oam_entity_registry_verified"] is True
    assert result.raw_provider_fields["oam_entity_lei_verified"] is False


@pytest.mark.parametrize("entities, identifiers", [
    ([], ["http://www.dcca.dk/cvr|99999999"]),                      # another company's CVR
    ([], [AAB_CVR_ID, "http://www.dcca.dk/cvr|99999999"]),          # mixed identifiers
    ([], []),                                                       # no identifier at all
    (["529900W18LQJJN6SJ336"], [AAB_CVR_ID]),                       # a foreign LEI is declared
])
def test_aab_registry_identity_fails_closed(monkeypatch, entities, identifiers):
    with pytest.raises(GlobalProviderError, match="unusable"):
        _aab_provider(monkeypatch, entities, identifiers).enrich_fundamentals(AAB_COMPANY)
