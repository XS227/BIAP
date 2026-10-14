from dataclasses import replace

import pytest

from global_markets.boerse_frankfurt_fundamentals import BoerseFrankfurtShareCountSupplement
from global_markets.models import GlobalCompany
from global_markets.providers import FundamentalsProvider, GlobalProviderError


class _Inner(FundamentalsProvider):
    provider_id = "inner"

    def __init__(self, **fields):
        self.fields = fields

    def enrich_fundamentals(self, company):
        return replace(company, **self.fields)


class _Source:
    limit = 12

    def __init__(self, payload=None, error=None):
        self.payload, self.error = payload, error

    def _url(self, isin, limit):
        return f"https://x/{isin}?limit={limit}"

    def _get_json(self, url):
        if self.error:
            raise GlobalProviderError("down")
        return self.payload

    @staticmethod
    def _row(payload):
        return max(payload["data"], key=lambda r: r["year"])


def _co():
    return GlobalCompany(country="DE", exchange="XETRA", currency="EUR", ticker="SAP", name="SAP", isin="DE0007164600")


def test_reviewed_row_gets_exchange_share_count_with_provenance():
    src = _Source({"isin": "DE0007164600", "data": [{"year": 2025, "outstandingShares": 1_166_000_000}]})
    out = BoerseFrankfurtShareCountSupplement(_Inner(net_income=7.0e9, eps=6.0), src).enrich_fundamentals(_co())
    assert out.shares_outstanding == 1_166_000_000
    assert out.raw_provider_fields["de_share_count_supplement"]["status"] == "applied"
    assert out.sources[-1].source_type == "official_exchange_share_count"


def test_existing_share_count_is_never_overwritten():
    src = _Source({"isin": "DE0007164600", "data": [{"year": 2025, "outstandingShares": 5}]})
    out = BoerseFrankfurtShareCountSupplement(_Inner(shares_outstanding=10.0), src).enrich_fundamentals(_co())
    assert out.shares_outstanding == 10.0


def test_contradicting_count_is_withheld_and_outage_is_recorded():
    src = _Source({"isin": "DE0007164600", "data": [{"year": 2025, "outstandingShares": 5_000_000_000}]})
    out = BoerseFrankfurtShareCountSupplement(_Inner(net_income=7.0e9, eps=6.0), src).enrich_fundamentals(_co())
    assert out.shares_outstanding is None
    assert out.raw_provider_fields["de_share_count_supplement"]["status"].startswith("withheld")
    down = BoerseFrankfurtShareCountSupplement(_Inner(), _Source(error=True)).enrich_fundamentals(_co())
    assert down.shares_outstanding is None
    assert down.raw_provider_fields["de_share_count_supplement"]["status"].startswith("unavailable")
