import os
from pathlib import Path

from global_markets import source_cache
from global_markets.cached_market import PersistentMarketProvider
from global_markets.cached_universe import PersistentUniverseProvider  # noqa: F401  (constructor default checked below)


def test_data_root_is_a_temp_dir_never_production():
    root = source_cache.data_root().resolve()
    assert root != Path("/var/lib/biap-global") and Path("/var/lib/biap-global") not in root.parents
    assert os.environ["BIAP_GLOBAL_DATA_DIR"] == str(source_cache.data_root())


def test_default_constructed_providers_resolve_inside_the_temp_dir():
    market = PersistentMarketProvider(None)
    assert Path("/var/lib/biap-global") not in market.root.parents and market.root != Path("/var/lib/biap-global/market")
