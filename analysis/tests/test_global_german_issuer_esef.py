"""German issuer-hosted ESEF registry: identity gates, Freiverkehr scope and
nested report packages (outer zip wrapping the .xbri, e.g. Deutsche Bank)."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import pytest

from global_markets.german_issuer_esef import (
    REGISTRY_PATH,
    GermanIssuerESEFProvider,
    IssuerPackage,
    load_registry,
)
from global_markets.models import GlobalCompany
from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling
from global_markets.providers import GlobalProviderError
from tests.test_global_evidence_pipeline import _ixbrl

LEI = "7LTWFZYICNSX8D621K86"
ROW = IssuerPackage(
    isin="DE0005140008", lei=LEI, ticker="DBK",
    package_url="https://investor-relations.db.com/x/Deutsche-Bank-AG-KA-KLB-ESEF-2025-12-31.zip",
    landing_url="https://www.db.com", period_end="2025-12-31", verified_at="2026-10-05T10:39:40+00:00",
)


def _company(**kw) -> GlobalCompany:
    base = dict(country="DE", exchange="XETRA", currency="EUR", ticker="DBK", name="DEUTSCHE BANK AG", isin="DE0005140008")
    base.update(kw)
    return GlobalCompany(**base)


def test_shipped_registry_is_valid():
    rows = load_registry(REGISTRY_PATH)
    assert rows
    for isin, row in rows.items():
        assert isin == row.isin and row.isin.startswith("DE") and len(row.lei) == 20
        assert row.package_url.startswith("https://") and row.period_end[:4].isdigit()


def test_registry_rejects_non_https(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"issuers": [{**ROW.__dict__, "package_url": "http://x.de/a.zip"}]}))
    with pytest.raises(ValueError):
        load_registry(path)


def test_open_market_listing_has_no_esef_obligation():
    provider = GermanIssuerESEFProvider(registry={})
    company = _company(ticker="XYZ", isin="DE000A0XYZ00", raw_provider_fields={"primary_market_mic": "FRAA"})
    with pytest.raises(GlobalProviderError, match="no ESEF annual financial report obligation"):
        provider.enrich_fundamentals(company)


def test_regulated_listing_without_reviewed_package_is_coverage_gap():
    provider = GermanIssuerESEFProvider(registry={})
    company = _company(ticker="XYZ", isin="DE000A0XYZ00", raw_provider_fields={"primary_market_mic": "XFRA"})
    with pytest.raises(GlobalProviderError, match="no reviewed issuer-published ESEF package"):
        provider.enrich_fundamentals(company)


def test_listing_lei_must_match_registry():
    provider = GermanIssuerESEFProvider(registry={ROW.isin: ROW})
    with pytest.raises(GlobalProviderError, match="LEI mismatch"):
        provider.enrich_fundamentals(_company(lei="529900AAAAAAAAAAAA00"))


def test_non_german_listing_rejected():
    provider = GermanIssuerESEFProvider(registry={ROW.isin: ROW})
    with pytest.raises(GlobalProviderError, match="DE listings only"):
        provider.enrich_fundamentals(_company(country="AT"))


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_outer_zip_wrapping_one_report_package_is_parsed():
    report = _ixbrl(LEI, date(2025, 12, 31)).encode()
    inner = _zip({"DB-2025-12-31/reports/report.xhtml": report})
    outer = _zip({"Deutsche_Bank_AG_KA+KLB_ESEF-2025-12-31.xbri": inner})
    filing = OAMFiling(oam="de-issuer", document_id="t", package_url=ROW.package_url, landing_url=ROW.landing_url)
    provider = NationalOAMESEFProvider(locators=[])
    with zipfile.ZipFile(io.BytesIO(outer)) as archive:
        payload = provider._parse_archive(filing, archive)
    assert LEI in payload["entities"]
    assert payload["reportFile"].endswith("report.xhtml")


def test_nested_packages_descend_only_one_level():
    report = _ixbrl(LEI, date(2025, 12, 31)).encode()
    deep = _zip({"a.zip": _zip({"b.xbri": _zip({"reports/r.xhtml": report})})})
    filing = OAMFiling(oam="de-issuer", document_id="t", package_url=ROW.package_url, landing_url=ROW.landing_url)
    with zipfile.ZipFile(io.BytesIO(deep)) as archive:
        with pytest.raises(GlobalProviderError, match="no XHTML report"):
            NationalOAMESEFProvider(locators=[])._parse_archive(filing, archive)
