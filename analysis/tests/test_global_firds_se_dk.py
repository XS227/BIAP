from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from global_markets.runtime import build_registry


def test_firds_supports_stockholm_and_copenhagen():
    provider = ESMAFIRDSOpenFIGIUniverseProvider()
    assert provider.supported("SE", "NASDAQ_STOCKHOLM")
    assert provider.supported("DK", "NASDAQ_COPENHAGEN")


def test_runtime_uses_authoritative_firds_for_stockholm_and_copenhagen():
    registry = build_registry()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
    ]:
        wrapper = registry.universe(country, exchange)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == "official-esma-firds-universe"
