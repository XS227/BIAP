from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_is_hkex_official_v22():
    assert CACHE_SCHEMA_VERSION == 22
