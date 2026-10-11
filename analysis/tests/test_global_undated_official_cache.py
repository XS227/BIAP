"""An "official" fundamentals snapshot without a filing period is not current.

Production regression (2026-10-11, NYSE:XOM): the successor registrant CIK had
no annual 10-K facts yet, an older parser still attached an empty SEC source,
and the persisted snapshot (officialEvidence=True, filingPeriodEnd=None) was
served as fresh and as the outage fallback. Börse Frankfurt year-only key data
is the one intentional undated official form and must keep working. Network is
never used.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import FundamentalsProvider, GlobalProviderError, append_source


def _seed(ticker: str = "XOM") -> GlobalCompany:
    return GlobalCompany(country="US", exchange="NYSE", currency="USD", ticker=ticker, name=ticker, mic_code="XNYS")


def _undated_official(company: GlobalCompany, **raw) -> GlobalCompany:
    return append_source(
        replace(company, raw_provider_fields={**company.raw_provider_fields, **raw}),
        SourceEvidence(
            provider="sec-edgar-xbrl-cached",
            source_type="official_regulatory_xbrl",
            source_id="CIK0002115436",
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0002115436.json",
            observed_at=None,
            period_end=None,
            quality=1.0,
        ),
    )


class _Upstream(FundamentalsProvider):
    provider_id = "test-upstream"

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result(company)


def _prime(tmp_path, **raw) -> None:
    PersistentFundamentalsProvider(_Upstream(lambda c: _undated_official(c, **raw)), data_dir=str(tmp_path)).enrich_fundamentals(_seed())


def test_undated_official_snapshot_is_not_fresh(tmp_path):
    _prime(tmp_path)
    upstream = _Upstream(error=GlobalProviderError("no annual period"))
    provider = PersistentFundamentalsProvider(upstream, data_dir=str(tmp_path))
    with pytest.raises(GlobalProviderError):
        provider.enrich_fundamentals(_seed())
    # The upstream was retried and the undated snapshot was not resurrected
    # as outage fallback.
    assert upstream.calls == 1


def test_year_only_official_snapshot_stays_fresh(tmp_path):
    _prime(tmp_path, de_bf_period_granularity="year_only")
    upstream = _Upstream(error=GlobalProviderError("must not be called"))
    provider = PersistentFundamentalsProvider(upstream, data_dir=str(tmp_path))
    result = provider.enrich_fundamentals(_seed())
    assert upstream.calls == 0
    assert result.raw_provider_fields["fundamentals_cache"] == "fresh"
