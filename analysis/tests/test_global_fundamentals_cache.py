from __future__ import annotations

from dataclasses import replace

from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import FundamentalsProvider, GlobalProviderError, append_source


def _seed() -> GlobalCompany:
    return GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD",
        ticker="TEST", name="Test Company",
    )


class OfficialProvider(FundamentalsProvider):
    provider_id = "official-test"

    def __init__(self):
        self.calls = 0

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        self.calls += 1
        enriched = replace(
            company,
            revenue=100.0,
            net_income=12.0,
            filing_period_end="2025-12-31",
            filing_observed_at="2026-02-01T00:00:00+00:00",
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_xbrl",
            source_id="filing-1",
            period_end="2025-12-31",
            quality=1.0,
        ))


class FailingProvider(FundamentalsProvider):
    provider_id = "failing-test"

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        raise GlobalProviderError("offline")


class VendorProvider(FundamentalsProvider):
    provider_id = "vendor-test"

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        enriched = replace(company, revenue=80.0, filing_period_end="2025-12-31")
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="public_vendor_financial_metrics",
            source_id="vendor-1",
            quality=0.7,
        ))


def test_official_snapshot_survives_upstream_outage(tmp_path):
    official = OfficialProvider()
    cache = PersistentFundamentalsProvider(official, data_dir=str(tmp_path), fresh_hours=0)
    first = cache.enrich_fundamentals(_seed())
    assert first.revenue == 100.0
    assert official.calls == 1

    fallback = PersistentFundamentalsProvider(FailingProvider(), data_dir=str(tmp_path), fresh_hours=0)
    restored = fallback.enrich_fundamentals(_seed())
    assert restored.revenue == 100.0
    assert any(source.source_type == "official_regulatory_xbrl" for source in restored.sources)
    assert any(source.source_type == "cache_snapshot" for source in restored.sources)


def test_vendor_snapshot_never_becomes_official_or_blocks_official_retry(tmp_path):
    vendor_cache = PersistentFundamentalsProvider(VendorProvider(), data_dir=str(tmp_path), fresh_hours=24)
    vendor_cache.enrich_fundamentals(_seed())
    info = vendor_cache.snapshot_info(_seed())
    assert info["officialEvidence"] is False

    official = OfficialProvider()
    official_cache = PersistentFundamentalsProvider(official, data_dir=str(tmp_path), fresh_hours=24)
    result = official_cache.enrich_fundamentals(_seed())
    assert official.calls == 1
    assert result.revenue == 100.0
    assert any(source.source_type == "official_regulatory_xbrl" for source in result.sources)


def test_market_sources_are_not_persisted_inside_fundamentals_snapshot(tmp_path):
    company = append_source(_seed(), SourceEvidence(
        provider="market-test", source_type="market_history", source_id="m1", quality=0.9,
    ))
    cache = PersistentFundamentalsProvider(OfficialProvider(), data_dir=str(tmp_path), fresh_hours=0)
    cache.enrich_fundamentals(company)

    restored = PersistentFundamentalsProvider(FailingProvider(), data_dir=str(tmp_path), fresh_hours=0).enrich_fundamentals(_seed())
    assert not any(source.provider == "market-test" for source in restored.sources)
