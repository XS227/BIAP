from global_markets.runtime import build_registry
from global_markets.sec_edgar import SECEdgarFundamentalsProvider


def test_us_sec_fundamentals_are_registered_without_env(monkeypatch):
    monkeypatch.delenv("BIAP_SEC_USER_AGENT", raising=False)
    registry = build_registry()

    nasdaq = registry.fundamentals("US", "NASDAQ")
    nyse = registry.fundamentals("US", "NYSE")

    assert isinstance(nasdaq, SECEdgarFundamentalsProvider)
    assert isinstance(nyse, SECEdgarFundamentalsProvider)
    assert nasdaq.user_agent
    assert nyse.user_agent
