from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_is_lse_official_v15():
    assert CACHE_SCHEMA_VERSION == 15
