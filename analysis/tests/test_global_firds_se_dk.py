from global_markets.nasdaq_nordic import NasdaqNordicUniverseProvider
from global_markets.runtime import build_registry


def test_nasdaq_official_supports_all_nordic_main_markets():
    provider = NasdaqNordicUniverseProvider()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ]:
        assert provider.supported(country, exchange)


def test_runtime_uses_authoritative_nasdaq_for_nordic_main_markets():
    registry = build_registry()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ]:
        wrapper = registry.universe(country, exchange)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == "official-nasdaq-nordic-main-market"
