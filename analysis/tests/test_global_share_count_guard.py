from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics


def _co(shares, eps=3.84, net_income=585.9e6):
    return GlobalCompany(country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="NXT",
                         name="Nextpower", price=86.11, reporting_currency="USD", eps=eps,
                         net_income=net_income, shares_outstanding=shares)


def test_stale_share_count_not_used_for_market_cap():
    out = _derive_metrics(_co(62_053_870.0))  # 2023 context, ~2.5x below NI/EPS = 152.6m
    assert out.market_cap is None and out.shares_outstanding is None
    assert any(d.startswith("shares_withheld") for d in out.raw_provider_fields["derived_metrics"])


def test_consistent_share_count_still_derives_market_cap():
    out = _derive_metrics(_co(152_000_000.0))
    assert out.market_cap == 86.11 * 152_000_000.0
    assert out.shares_outstanding == 152_000_000.0


def test_dual_class_within_tolerance_kept():
    out = _derive_metrics(_co(190_000_000.0))  # 1.25x: preferred dividends / class differences
    assert out.shares_outstanding == 190_000_000.0

