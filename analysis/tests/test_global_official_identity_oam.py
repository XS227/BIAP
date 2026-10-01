"""Regression: official evidence must be reachable from ISIN, not ticker/name.

Covers the shared-layer failures that produced ``missing=fundamental_source``
for issuers whose official ESEF report existed (AKTIA, BIRG, French and
Spanish issuers): ISIN -> issuer LEI via ESMA FIRDS, the French AMF OAM
locator, and the refusal to treat an untagged report as official evidence.
"""
from __future__ import annotations

import sqlite3

import pytest

from global_markets import firds_lei_index
from global_markets.esef_country import CountryAwareESEFFundamentalsProvider
from global_markets.gleif import LEIResolution
from global_markets.models import GlobalCompany
from global_markets.oam_esef import FranceAMFInfoFinanciereLocator, NationalOAMESEFProvider, OAMFiling, OAMLocator
from global_markets.providers import GlobalProviderError


def _index(tmp_path, monkeypatch, rows):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    path = firds_lei_index.index_path()
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE isin_lei (isin TEXT PRIMARY KEY, lei TEXT NOT NULL, name TEXT)")
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        db.executemany("INSERT INTO isin_lei VALUES (?, ?, ?)", rows)
        from datetime import datetime, timezone
        db.execute("INSERT INTO meta VALUES ('builtAt', ?)", (datetime.now(timezone.utc).isoformat(),))


def test_firds_index_maps_isin_to_issuer_lei(tmp_path, monkeypatch):
    _index(tmp_path, monkeypatch, [("FI4000058870", "743700GC62JLHFBUND16", "Aktia Pankki Oyj")])
    assert firds_lei_index.lookup_issuer_lei("fi4000058870", allow_build=False) == "743700GC62JLHFBUND16"
    assert firds_lei_index.lookup_issuer_lei("FI0000000000", allow_build=False) is None
    assert firds_lei_index.lookup_issuer_lei("BAD", allow_build=False) is None


def test_display_name_abbreviation_resolves_through_firds_isin(tmp_path, monkeypatch):
    # Venue display name "BANK OF IRELAND GP" is not a legal name; the ISIN is.
    _index(tmp_path, monkeypatch, [("IE00BD1RP616", "635400C8EK6DRI12LJ39", "BANK OF IRELAND GROUP")])
    provider = CountryAwareESEFFundamentalsProvider.__new__(CountryAwareESEFFundamentalsProvider)

    class _Gleif:
        def resolve_isin(self, isin, country=None):
            raise GlobalProviderError("no GLEIF ISIN mapping")

        def verify_lei(self, lei):
            return LEIResolution(lei=lei, legal_name="Bank of Ireland Group public limited company", entity_status="ACTIVE", registration_status="ISSUED", source_url="https://api.gleif.org")

        def __getattr__(self, name):
            raise GlobalProviderError(f"name resolution must not be used ({name})")

    provider.gleif = _Gleif()
    company = GlobalCompany(country="IE", exchange="EURONEXT_DUBLIN", currency="EUR", ticker="BIRG",
                            name="BANK OF IRELAND GP", isin="IE00BD1RP616")
    lei, legal = provider._resolve_lei(company)
    assert lei == "635400C8EK6DRI12LJ39"
    assert legal.startswith("Bank of Ireland Group")


class _Http:
    def __init__(self, payload):
        self.payload = payload
        self.keys = []

    def cached_text(self, key, fetch):
        import json
        self.keys.append(key)
        return json.dumps(self.payload)


def test_amf_locator_keeps_only_esef_documents_by_lei():
    rows = [
        {"url_de_recuperation": "https://fr.ftp.opendatasoft.com/datadila/INFOFI/X/2026/04/FCX1_20260423.zip",
         "informationdeposee_inf_dat_emt": "2026-04-23T10:00:00+00:00", "fichierdecontenu_inf_fic_nom": "FCX1_20260423.zip",
         "informationdeposee_inf_tit_inf": "Rapport financier annuel 2025"},
        {"url_de_recuperation": "https://fr.ftp.opendatasoft.com/datadila/INFOFI/X/2026/04/FCX2_20260423.pdf",
         "informationdeposee_inf_dat_emt": "2026-04-23T10:00:00+00:00"},
    ]
    locator = FranceAMFInfoFinanciereLocator(_Http({"results": rows}))
    company = GlobalCompany(country="FR", exchange="EURONEXT_PARIS", currency="EUR", ticker="OREGE", name="OREGE", isin="FR0010609206")
    filings = locator.annual_filings(company, "969500RXF62TC04Z7S84", "OREGE")
    assert [f.document_id for f in filings] == ["AMF-INFOFI:FCX1_20260423.zip"]
    from urllib.parse import unquote_plus
    assert 'identificationsociete_iso_cd_lei="969500RXF62TC04Z7S84"' in unquote_plus(locator.http.keys[0])


def test_amf_locator_without_esef_report_raises_official_unavailable():
    locator = FranceAMFInfoFinanciereLocator(_Http({"results": []}))
    company = GlobalCompany(country="FR", exchange="EURONEXT_PARIS", currency="EUR", ticker="X", name="X")
    with pytest.raises(GlobalProviderError, match="no ESEF annual financial report"):
        locator.annual_filings(company, "969500RXF62TC04Z7S84", "X")


class _FR(OAMLocator):
    oam = "fr-test"
    country = "FR"

    def __init__(self):
        pass

    def annual_filings(self, company, lei, legal_name):
        return [OAMFiling(oam=self.oam, document_id="AMF:1", package_url="https://x/1.xhtml", landing_url="https://x/1.xhtml")]


def test_untagged_official_report_is_not_official_evidence(monkeypatch):
    provider = NationalOAMESEFProvider(locators=[_FR()])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: ("8945008D5R6WV7EXRN47", "AELIS FARMA"))
    monkeypatch.setattr(provider, "package_facts", lambda filing: {"facts": [], "entities": []})
    company = GlobalCompany(country="FR", exchange="EURONEXT_PARIS", currency="EUR", ticker="AELIS", name="AELIS FARMA")
    with pytest.raises(GlobalProviderError, match="no inline XBRL"):
        provider.enrich_fundamentals(company)
