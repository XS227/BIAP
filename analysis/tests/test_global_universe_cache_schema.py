from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_is_bist_official_v14():
    assert CACHE_SCHEMA_VERSION == 14
