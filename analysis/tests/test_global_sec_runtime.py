from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.runtime import build_registry
from global_markets.sec_edgar import SECEdgarFundamentalsProvider


def test_us_sec_fundamentals_are_registered_without_env(monkeypatch):
    monkeypatch.delenv("BIAP_SEC_USER_AGENT", raising=False)
    registry = build_registry()

    nasdaq = registry.fundamentals("US", "NASDAQ")
    nyse = registry.fundamentals("US", "NYSE")

    assert isinstance(nasdaq, PersistentFundamentalsProvider)
    assert isinstance(nyse, PersistentFundamentalsProvider)
    assert isinstance(nasdaq.upstream, SECEdgarFundamentalsProvider)
    assert isinstance(nyse.upstream, SECEdgarFundamentalsProvider)
    assert nasdaq.upstream.user_agent
    assert nyse.upstream.user_agent
