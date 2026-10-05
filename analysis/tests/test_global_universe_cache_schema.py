from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_is_jse_official_v23():
    assert CACHE_SCHEMA_VERSION == 23
