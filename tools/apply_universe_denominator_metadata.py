from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Persist provider-level completeness metadata. This prevents a resolver-matched
# subset from silently becoming the denominator for market coverage.
replace_once(
    "analysis/global_markets/cached_universe.py",
    '''        payload = {\n            "schemaVersion": CACHE_SCHEMA_VERSION,\n            "country": country.upper(),\n            "exchange": exchange.upper(),\n            "provider": self.upstream.provider_id,\n            "fetchedAt": now,\n            "count": len(rows),\n            "instruments": [self._row(row) for row in rows],\n        }\n''',
    '''        upstream_metadata = getattr(self.upstream, "last_metadata", {})\n        metadata = dict(upstream_metadata) if isinstance(upstream_metadata, dict) else {}\n        try:\n            official_count = max(len(rows), int(metadata.get("officialCount") or len(rows)))\n        except (TypeError, ValueError):\n            official_count = len(rows)\n        metadata["officialCount"] = official_count\n        metadata["resolvedCount"] = len(rows)\n        metadata["resolutionCoveragePct"] = round(100.0 * len(rows) / official_count, 2) if official_count else 0.0\n        payload = {\n            "schemaVersion": CACHE_SCHEMA_VERSION,\n            "country": country.upper(),\n            "exchange": exchange.upper(),\n            "provider": self.upstream.provider_id,\n            "fetchedAt": now,\n            "count": len(rows),\n            "metadata": metadata,\n            "instruments": [self._row(row) for row in rows],\n        }\n''',
)

replace_once(
    "analysis/global_markets/cached_universe.py",
    '''        return {\n            "available": True,\n            "provider": str(payload.get("provider") or self.upstream.provider_id),\n            "fetchedAt": payload.get("fetchedAt"),\n            "count": int(payload.get("count") or 0),\n            "ageHours": None if age is None else round(age / 3600.0, 2),\n            "fresh": self._is_fresh(payload),\n            "schemaVersion": CACHE_SCHEMA_VERSION,\n        }\n''',
    '''        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}\n        count = int(payload.get("count") or 0)\n        try:\n            official_count = max(count, int(metadata.get("officialCount") or count))\n        except (TypeError, ValueError):\n            official_count = count\n        try:\n            resolved_count = int(metadata.get("resolvedCount") or count)\n        except (TypeError, ValueError):\n            resolved_count = count\n        coverage = round(100.0 * resolved_count / official_count, 2) if official_count else 0.0\n        return {\n            "available": True,\n            "provider": str(payload.get("provider") or self.upstream.provider_id),\n            "fetchedAt": payload.get("fetchedAt"),\n            "count": count,\n            "officialCount": official_count,\n            "resolvedCount": resolved_count,\n            "resolutionCoveragePct": coverage,\n            "metadata": metadata,\n            "ageHours": None if age is None else round(age / 3600.0, 2),\n            "fresh": self._is_fresh(payload),\n            "schemaVersion": CACHE_SCHEMA_VERSION,\n        }\n''',
)

# Scanner denominator comes from officialCount when an authoritative provider
# exposes it. Mapped/resolved rows remain the quote candidates.
replace_once(
    "analysis/global_markets/scanner.py",
    '''        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))\n        discovered_count = len(universe)\n        selected_universe = universe[:discovery_limit]\n        partial = discovered_count > discovery_limit\n''',
    '''        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))\n        resolved_count = len(universe)\n        snapshot_info_fn = getattr(universe_provider, "snapshot_info", None)\n        universe_info = snapshot_info_fn(country=country.upper(), exchange=spec.code) if callable(snapshot_info_fn) else {}\n        try:\n            official_count = max(resolved_count, int((universe_info or {}).get("officialCount") or resolved_count))\n        except (TypeError, ValueError):\n            official_count = resolved_count\n        discovered_count = official_count\n        selected_universe = universe[:discovery_limit]\n        partial = official_count > discovery_limit\n''',
)

# Expose both official and resolved counts so UI/diagnostics cannot confuse them.
replace_once(
    "analysis/global_markets/scanner.py",
    '''                "universeDiscovered": discovered_count,\n                "universeScreened": len(cached_quotes),\n''',
    '''                "universeDiscovered": discovered_count,\n                "universeResolved": resolved_count,\n                "universeScreened": len(cached_quotes),\n''',
)
replace_once(
    "analysis/global_markets/scanner.py",
    '''            "universeDiscovered": discovered_count,\n            "universeScreened": len(quotes),\n''',
    '''            "universeDiscovered": discovered_count,\n            "universeResolved": resolved_count,\n            "universeScreened": len(quotes),\n''',
)
