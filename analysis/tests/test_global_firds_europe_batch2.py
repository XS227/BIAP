from pathlib import Path
import json

from global_markets.cached_universe import CACHE_SCHEMA_VERSION, PersistentUniverseProvider
from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from global_markets.providers import InstrumentUniverseProvider
from global_markets.runtime import build_registry


BATCH2 = [
    ("NL", "EURONEXT_AMSTERDAM"),
    ("BE", "EURONEXT_BRUSSELS"),
    ("PT", "EURONEXT_LISBON"),
    ("NO", "EURONEXT_OSLO"),
    ("ES", "BME_MADRID"),
]


def test_firds_batch2_supported():
    for country, exchange in BATCH2:
        assert ESMAFIRDSOpenFIGIUniverseProvider.supported(country, exchange)


def test_firds_batch2_registry_is_authoritative():
    registry = build_registry()
    for country, exchange in BATCH2:
        provider = registry.universe(country, exchange)
        upstream = getattr(provider, "upstream", provider)
        assert getattr(upstream, "provider_id", None) == "official-esma-firds-universe"
        assert getattr(provider, "fresh_seconds", 0) >= 167 * 3600


def test_suspect_nordic_markets_are_not_promoted_to_firds_yet():
    registry = build_registry()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
        ("IE", "EURONEXT_DUBLIN"),
    ]:
        provider = registry.universe(country, exchange)
        upstream = getattr(provider, "upstream", provider)
        assert getattr(upstream, "provider_id", None) != "official-esma-firds-universe"


class ProviderA(InstrumentUniverseProvider):
    provider_id = "provider-a"
    def list_instruments(self, *, country=None, exchange=None):
        return []


class ProviderB(InstrumentUniverseProvider):
    provider_id = "provider-b"
    def list_instruments(self, *, country=None, exchange=None):
        return []


def test_cache_rejects_snapshot_from_different_upstream_provider(tmp_path: Path):
    a = PersistentUniverseProvider(ProviderA(), data_dir=str(tmp_path))
    path = a._path("NL", "EURONEXT_AMSTERDAM")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "country": "NL",
        "exchange": "EURONEXT_AMSTERDAM",
        "provider": "provider-a",
        "fetchedAt": "2026-09-23T00:00:00+00:00",
        "count": 0,
        "metadata": {},
        "instruments": [],
    }), encoding="utf-8")

    b = PersistentUniverseProvider(ProviderB(), data_dir=str(tmp_path))
    assert b._read_payload("NL", "EURONEXT_AMSTERDAM") is None
