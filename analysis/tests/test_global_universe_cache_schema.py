from global_markets.cached_universe import CACHE_SCHEMA_VERSION


def test_global_universe_cache_schema_is_firds_nordics_v12():
    assert CACHE_SCHEMA_VERSION == 12
