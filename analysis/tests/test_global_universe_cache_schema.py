from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_persists_de_reporting_market_v24():
    assert CACHE_SCHEMA_VERSION == 24
