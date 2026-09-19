from pathlib import Path

import pytest

from global_markets.edinet import EDINETClient
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.verified_filing_drop import VerifiedFilingDropProvider


def test_edinet_requires_real_api_key(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    with pytest.raises(GlobalProviderError):
        EDINETClient(api_key="")


def test_verified_filing_drop_rejects_unverified_record(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    folder = tmp_path / "filings" / "AU"
    folder.mkdir(parents=True)
    (folder / "BHP.json").write_text(
        '{"verified": false, "sourceProvider":"asx", "sourceUrl":"https://example.invalid", "periodEnd":"2026-06-30", "fundamentals":{"revenue":1}}',
        encoding="utf-8",
    )
    provider = VerifiedFilingDropProvider(country="AU", provider_names=("asx", "issuer"))
    company = GlobalCompany(country="AU", exchange="ASX", currency="AUD", ticker="BHP", name="BHP")
    with pytest.raises(GlobalProviderError):
        provider.enrich_fundamentals(company)


def test_verified_filing_drop_accepts_only_with_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    folder = tmp_path / "filings" / "AU"
    folder.mkdir(parents=True)
    (folder / "BHP.json").write_text(
        '{"verified": true, "sourceProvider":"asx", "sourceUrl":"https://www.asx.com.au/", "sourceId":"fixture", "periodEnd":"2026-06-30", "observedAt":"2026-08-20T00:00:00Z", "currency":"AUD", "fundamentals":{"revenue":1000,"net_income":100}}',
        encoding="utf-8",
    )
    provider = VerifiedFilingDropProvider(country="AU", provider_names=("asx", "issuer"))
    company = GlobalCompany(country="AU", exchange="ASX", currency="AUD", ticker="BHP", name="BHP")
    enriched = provider.enrich_fundamentals(company)
    assert enriched.revenue == 1000
    assert enriched.net_income == 100
    assert enriched.sources[-1].provider == "asx"


def test_verified_filing_drop_preserves_issuer_source_type(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    folder = tmp_path / "filings" / "SG"
    folder.mkdir(parents=True)
    (folder / "S68.json").write_text(
        '{"verified":true,"sourceProvider":"sgx-official-issuer-financial-information",'
        '"sourceType":"official_issuer_fundamentals","sourceUrl":"https://investorrelations.sgx.com/financial-information",'
        '"sourceId":"S68:FY2026","periodEnd":"2026-06-30","observedAt":"2026-08-06T00:00:00Z",'
        '"currency":"SGD","fundamentals":{"revenue":1559000000,"operating_income":887000000}}',
        encoding="utf-8",
    )
    provider = VerifiedFilingDropProvider(
        country="SG",
        provider_names=("sgx-official-issuer-financial-information",),
    )
    company = GlobalCompany(country="SG", exchange="SGX", currency="SGD", ticker="S68", name="Singapore Exchange Ltd.")
    enriched = provider.enrich_fundamentals(company)
    assert enriched.revenue == 1559000000
    assert enriched.sources[-1].source_type == "official_issuer_fundamentals"
    assert enriched.raw_provider_fields["verified_filing_verification_mode"] is None


def test_verified_filing_drop_exposes_bundled_snapshot_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    folder = tmp_path / "filings" / "DE"
    folder.mkdir(parents=True)
    (folder / "ALV.json").write_text(
        '{"verified":true,"verificationMode":"bundled_verified_snapshot",'
        '"sourceProvider":"de-official-issuer-financials",'
        '"sourceType":"official_issuer_financial_statement",'
        '"sourceUrl":"https://www.allianz.com/en/investor_relations/results-reports/financial-statements.html",'
        '"sourceId":"allianz-fy2025-financial-statements","periodEnd":"2025-12-31",'
        '"observedAt":"2026-03-13T00:00:00Z","currency":"EUR",'
        '"fundamentals":{"revenue":102802000000,"net_income":11430000000}}',
        encoding="utf-8",
    )
    provider = VerifiedFilingDropProvider(
        country="DE",
        provider_names=("de-official-issuer-financials",),
    )
    company = GlobalCompany(country="DE", exchange="XETRA", currency="EUR", ticker="ALV", name="Allianz SE")
    enriched = provider.enrich_fundamentals(company)
    assert enriched.raw_provider_fields["verified_filing_verification_mode"] == "bundled_verified_snapshot"
