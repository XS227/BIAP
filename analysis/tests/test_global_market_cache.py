from dataclasses import replace
from datetime import datetime, timezone

import pytest

from global_markets.cached_market import PersistentMarketProvider
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import GlobalProviderError, MarketDataProvider


class FakeMarket(MarketDataProvider):
    provider_id = "fake-market"

    def __init__(self):
        self.fail = False
        self.calls = 0

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        self.calls += 1
        if self.fail:
            raise GlobalProviderError("upstream unavailable")
        return replace(
            company,
            price=123.45,
            price_observed_at=datetime.now(timezone.utc).isoformat(),
            avg_volume_30d=1000000,
            price_52w_high=150.0,
            price_52w_low=90.0,
            volatility_annualized_pct=24.0,
            max_drawdown_pct=-18.0,
            pe=21.5,
            sources=[
                *company.sources,
                SourceEvidence(
                    provider=self.provider_id,
                    source_type="daily_market_history",
                    source_id=company.identity(),
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    quality=0.95,
                ),
            ],
        )


def seed() -> GlobalCompany:
    return GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="TEST",
        name="Test Corp",
        sources=[SourceEvidence(provider="catalog", source_type="instrument_reference", quality=0.9)],
    )


def test_market_cache_serves_fresh_snapshot_without_second_upstream_call(tmp_path):
    upstream = FakeMarket()
    provider = PersistentMarketProvider(upstream, data_dir=str(tmp_path), fresh_hours=6)

    first = provider.enrich_market(seed())
    second = provider.enrich_market(seed())

    assert upstream.calls == 1
    assert first.price == pytest.approx(123.45)
    assert second.price == pytest.approx(123.45)
    assert second.raw_provider_fields["market_cache"] == "fresh"
    assert any(source.source_type == "daily_market_history_cache" for source in second.sources)


def test_market_cache_falls_back_to_last_verified_snapshot(tmp_path):
    upstream = FakeMarket()
    provider = PersistentMarketProvider(upstream, data_dir=str(tmp_path), fresh_hours=0)

    first = provider.enrich_market(seed())
    upstream.fail = True
    fallback = provider.enrich_market(seed())

    assert first.price == pytest.approx(123.45)
    assert fallback.price == pytest.approx(123.45)
    assert fallback.price_observed_at == first.price_observed_at
    assert fallback.raw_provider_fields["market_cache"] == "fallback"
    assert fallback.raw_provider_fields["market_upstream_provider"] == "fake-market"
    cache_sources = [s for s in fallback.sources if s.source_type == "daily_market_history_cache"]
    assert cache_sources
    assert "fallback" in (cache_sources[-1].notes or "").lower()


def test_market_cache_refuses_unverified_price_snapshot(tmp_path):
    class BadMarket(MarketDataProvider):
        provider_id = "bad-market"
        def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
            return replace(company, price=10.0, price_observed_at=None)

    provider = PersistentMarketProvider(BadMarket(), data_dir=str(tmp_path), fresh_hours=0)
    with pytest.raises(GlobalProviderError):
        provider.enrich_market(seed())
