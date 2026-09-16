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
