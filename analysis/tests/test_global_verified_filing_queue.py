from __future__ import annotations

import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.verified_filing_drop import VerifiedFilingDropProvider


def _company() -> GlobalCompany:
    return GlobalCompany(
        country="DE",
        exchange="FRANKFURT",
        mic_code="XFRA",
        currency="EUR",
        ticker="AUTO",
        name="AUTO TEST AG",
        isin="DE0000000001",
        raw_provider_fields={"reporting_market": "FRAA", "market_segment": "082"},
    )


def test_missing_german_filing_is_queued_once_and_refreshed(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    provider = VerifiedFilingDropProvider(
        country="DE",
        provider_names=("unternehmensregister-de-auto",),
        enqueue_missing=True,
        queue_name="de-fundamentals-missing",
    )

    with pytest.raises(GlobalProviderError, match="discovery queued"):
        provider.enrich_fundamentals(_company())

    queue_path = tmp_path / "source-index" / "de-fundamentals-missing.json"
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    row = payload["DE0000000001"]
    assert row["ticker"] == "AUTO"
    assert row["name"] == "AUTO TEST AG"
    assert row["reportingMarket"] == "FRAA"
    assert row["status"] == "pending"
    assert row["firstSeenAt"]
    assert row["lastSeenAt"]


def test_auto_discovered_verified_filing_is_reused_from_persistent_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    filing_dir = tmp_path / "filings" / "DE"
    filing_dir.mkdir(parents=True)
    (filing_dir / "AUTO.json").write_text(
        json.dumps(
            {
                "verified": True,
                "sourceProvider": "unternehmensregister-de-auto",
                "sourceType": "official_regulatory_financial_statement",
                "sourceId": "UR:DE0000000001:2025",
                "sourceUrl": "https://www.unternehmensregister.de/",
                "periodEnd": "2025-12-31",
                "observedAt": "2026-04-01T00:00:00+00:00",
                "currency": "EUR",
                "reportScope": "consolidated",
                "quality": 0.98,
                "provenanceStatus": "independently_verified",
                "auditStatus": "audited",
                "sector": "Industrials",
                "industry": "Machinery",
                "rawProviderFields": {"de_auto_resolver": True},
                "fundamentals": {
                    "revenue": 100000000,
                    "net_income": 8000000,
                    "total_assets": 150000000,
                    "total_liabilities": 90000000,
                    "total_equity": 60000000,
                    "retained_earnings": 20000000,
                    "current_assets": 70000000,
                    "current_liabilities": 40000000,
                },
            }
        ),
        encoding="utf-8",
    )
    provider = VerifiedFilingDropProvider(
        country="DE",
        provider_names=("unternehmensregister-de-auto",),
        enqueue_missing=True,
        queue_name="de-fundamentals-missing",
    )

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.revenue == 100000000
    assert enriched.retained_earnings == 20000000
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sector == "Industrials"
    assert enriched.raw_provider_fields["de_auto_resolver"] is True
    assert enriched.sources[-1].provider == "unternehmensregister-de-auto"
    assert enriched.sources[-1].audit_status == "audited"
