from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.jse_issuer import parse_sibanye_2025, JSEIssuerFundamentalsProvider
from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.runtime import build_registry


SAMPLE = """
CONSOLIDATED INCOME STATEMENT
Revenue 129,677 112,129
Loss for the year (4,708) (5,721)
CONSOLIDATED STATEMENT OF FINANCIAL POSITION
Cash and cash equivalents 17,178 16,049
Total assets 149,737 138,088
Total liabilities 105,570 89,799
Total equity 44,167 48,289
"""


def test_sibanye_2025_primary_totals_parse_and_reconcile():
    metrics = parse_sibanye_2025(SAMPLE)
    assert metrics["revenue"] == 129_677_000_000.0
    assert metrics["net_income"] == -5_171_000_000.0
    assert metrics["total_assets"] == 149_737_000_000.0
    assert metrics["total_liabilities"] == 105_570_000_000.0
    assert metrics["total_equity"] == 44_167_000_000.0


def test_za_runtime_prefers_jse_issuer_before_sec_and_vendor():
    provider = build_registry().fundamentals("ZA", "JSE")
    assert isinstance(provider, PersistentFundamentalsProvider)
    outer = provider.upstream
    assert isinstance(outer, FallbackFundamentalsProvider)
    official = outer.primary
    assert isinstance(official, FallbackFundamentalsProvider)
    assert isinstance(official.primary, JSEIssuerFundamentalsProvider)
