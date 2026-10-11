"""Regression: the shared cross-market fundamentals cache preserves distress inputs."""
from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.models import GlobalCompany


class _Stub:
    provider_id = 'stub-official'

    def enrich_fundamentals(self, company):
        return company


def test_retained_earnings_survives_global_fundamentals_cache(tmp_path):
    provider = PersistentFundamentalsProvider(_Stub(), data_dir=str(tmp_path))
    company = GlobalCompany(country='US', exchange='NYSE', currency='USD', ticker='TEST', name='Test',
                            retained_earnings=125.0, total_assets=500.0, total_liabilities=200.0)
    provider._write(company)
    stored = provider._read(company)
    assert stored['fundamentals']['retained_earnings'] == 125.0
    restored = provider._decode(company.__class__(country='US', exchange='NYSE', currency='USD', ticker='TEST', name='Test'), stored, fallback=False)
    assert restored.retained_earnings == 125.0
    assert restored.total_liabilities == 200.0
