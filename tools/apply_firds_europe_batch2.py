from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:220]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Expand the ESMA FIRDS native/relevant venue map only to markets whose probe
# produced plausible regulated/native ordinary-share populations.
replace_once(
    "analysis/global_markets/esma_firds_universe.py",
    '''    ("PT", "EURONEXT_LISBON"): "XLIS",\n}\n''',
    '''    ("PT", "EURONEXT_LISBON"): "XLIS",\n    ("NO", "EURONEXT_OSLO"): "XOSL",\n    ("ES", "BME_MADRID"): "XMAD",\n}\n''',
)

# Reuse the weekly FIRDS provider for the validated second batch. Sweden,
# Denmark, Finland, Iceland and Ireland stay on the non-authoritative reference
# path until their official exchange-native source is integrated/validated.
replace_once(
    "analysis/global_markets/runtime.py",
    '''    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)\n    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)\n\n''',
    '''    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)\n    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)\n    registry.register_universe("NL", "EURONEXT_AMSTERDAM", firds_eu)\n    registry.register_universe("BE", "EURONEXT_BRUSSELS", firds_eu)\n    registry.register_universe("PT", "EURONEXT_LISBON", firds_eu)\n    registry.register_universe("NO", "EURONEXT_OSLO", firds_eu)\n    registry.register_universe("ES", "BME_MADRID", firds_eu)\n\n''',
)

# Cache snapshots belong to the provider that produced them. This prevents a
# fresh vendor-reference snapshot from surviving a runtime migration to an
# official universe provider simply because the country/exchange path matches.
replace_once(
    "analysis/global_markets/cached_universe.py",
    '''        if str(payload.get("exchange") or "").upper() != exchange.upper():\n            return None\n        if not isinstance(payload.get("instruments"), list):\n            return None\n''',
    '''        if str(payload.get("exchange") or "").upper() != exchange.upper():\n            return None\n        expected_provider = str(getattr(self.upstream, "provider_id", "") or "")\n        cached_provider = str(payload.get("provider") or "")\n        if expected_provider and cached_provider != expected_provider:\n            return None\n        if not isinstance(payload.get("instruments"), list):\n            return None\n''',
)

# Add regression tests without network access.
test_path = Path("analysis/tests/test_global_firds_europe_batch2.py")
test_path.write_text(r'''from pathlib import Path
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
''', encoding="utf-8")
