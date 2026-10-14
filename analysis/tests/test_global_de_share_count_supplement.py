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


def test_owners_share_of_net_income_is_used_when_recorded():
    # Total net income includes a large non-controlling share (Cenit-like):
    # -2,452k / -0.14 implies 17.5M shares, owners' -1,210k implies 8.6M.
    src = _Source({"isin": "DE0007164600", "data": [{"year": 2025, "outstandingShares": 8_370_000}]})
    withheld = BoerseFrankfurtShareCountSupplement(
        _Inner(net_income=-2_452_000.0, eps=-0.14), src).enrich_fundamentals(_co())
    assert withheld.shares_outstanding is None
    applied = BoerseFrankfurtShareCountSupplement(
        _Inner(net_income=-2_452_000.0, eps=-0.14,
               raw_provider_fields={"net_income_attributable_to_owners": -1_210_000}), src).enrich_fundamentals(_co())
    assert applied.shares_outstanding == 8_370_000
    assert applied.raw_provider_fields["de_share_count_supplement"]["earnings_basis"] == "net_income_attributable_to_owners"


def test_owners_share_does_not_bypass_contradiction_check():
    src = _Source({"isin": "DE0007164600", "data": [{"year": 2025, "outstandingShares": 50_000_000}]})
    out = BoerseFrankfurtShareCountSupplement(
        _Inner(net_income=-2_452_000.0, eps=-0.14,
               raw_provider_fields={"net_income_attributable_to_owners": -1_210_000}), src).enrich_fundamentals(_co())
    assert out.shares_outstanding is None
