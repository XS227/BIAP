from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:220]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Runtime registration: FIRDS is authoritative membership; OpenFIGI only resolves
# local symbols. Keep the cache fresh for one weekly FIRDS full-file cycle.
replace_once(
    "analysis/global_markets/runtime.py",
    "from .edinet import EDINETFundamentalsProvider\n",
    "from .edinet import EDINETFundamentalsProvider\nfrom .esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider\n",
)
replace_once(
    "analysis/global_markets/runtime.py",
    '''    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())\n    registry.register_universe("AU", "ASX", asx_universe)\n\n''',
    '''    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())\n    registry.register_universe("AU", "ASX", asx_universe)\n\n    # France and Italy: ESMA FIRDS is the authoritative regulated/native common-\n    # share membership source. OpenFIGI is used only to resolve the local ticker.\n    # Cache for one FIRDS full-file cycle so an app request never has to resolve\n    # hundreds of ISINs synchronously under the unauthenticated OpenFIGI limit.\n    firds_eu = PersistentUniverseProvider(\n        ESMAFIRDSOpenFIGIUniverseProvider(),\n        fresh_hours=168,\n    )\n    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)\n    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)\n\n''',
)

# Semantics changed for FR/IT from vendor MIC catalogue to official FIRDS native
# common-share identity. Force older snapshots out immediately.
replace_once(
    "analysis/global_markets/cached_universe.py",
    "# Version 8 invalidates pre-strict-MIC snapshots. Earlier caches could contain\n# instruments whose exchange membership was inferred from a broad country/text\n# query instead of being proven by an accepted venue MIC.\nCACHE_SCHEMA_VERSION = 9\n",
    "# Version 10 invalidates pre-FIRDS France/Italy snapshots. Those older caches\n# could be MIC-correct yet still include secondary/cross-listed lines. Current\n# official-market caches preserve authoritative membership and resolver coverage.\nCACHE_SCHEMA_VERSION = 10\n",
)
replace_once(
    "analysis/tests/test_global_universe_cache_v8.py",
    "def test_universe_cache_schema_is_v9():\n    assert CACHE_SCHEMA_VERSION == 9\n",
    "def test_universe_cache_schema_is_v10():\n    assert CACHE_SCHEMA_VERSION == 10\n",
)

# The scheduled source job should refresh FIRDS weekly, not resolve hundreds of
# ISINs every day. Other universe providers keep their existing refresh cadence.
replace_once(
    "analysis/global_markets/universe_sync.py",
    '''        try:\n            provider = registry.universe(country, exchange)\n            if hasattr(provider, "refresh"):\n                rows = provider.refresh(country=country, exchange=exchange)\n            else:\n                rows = list(provider.list_instruments(country=country, exchange=exchange))\n''',
    '''        try:\n            provider = registry.universe(country, exchange)\n            upstream = getattr(provider, "upstream", provider)\n            upstream_id = str(getattr(upstream, "provider_id", ""))\n            if upstream_id == "official-esma-firds-universe" and hasattr(provider, "snapshot_info"):\n                existing = provider.snapshot_info(country=country, exchange=exchange)\n                if isinstance(existing, dict) and existing.get("available") and existing.get("fresh"):\n                    print(\n                        f"UNIVERSE_SYNC skip-fresh {country}:{exchange} "\n                        f"official={existing.get('officialCount')} resolved={existing.get('resolvedCount')} "\n                        f"coverage={existing.get('resolutionCoveragePct')}%"\n                    )\n                    ok += 1\n                    continue\n            if hasattr(provider, "refresh"):\n                rows = provider.refresh(country=country, exchange=exchange)\n            else:\n                rows = list(provider.list_instruments(country=country, exchange=exchange))\n''',
)

# More useful sync diagnostics for authoritative universes.
replace_once(
    "analysis/global_markets/universe_sync.py",
    '''            print(\n                f"UNIVERSE_SYNC ok {country}:{exchange} count={len(rows)} "\n                f"cached_at={info.get('fetchedAt') if isinstance(info, dict) else None}"\n            )\n''',
    '''            print(\n                f"UNIVERSE_SYNC ok {country}:{exchange} count={len(rows)} "\n                f"official={info.get('officialCount') if isinstance(info, dict) else None} "\n                f"resolved={info.get('resolvedCount') if isinstance(info, dict) else None} "\n                f"coverage={info.get('resolutionCoveragePct') if isinstance(info, dict) else None}% "\n                f"cached_at={info.get('fetchedAt') if isinstance(info, dict) else None}"\n            )\n''',
)
