"""Refresh persistent BIAP Global instrument-universe snapshots.

Usage:
    python -m global_markets.universe_sync

BIAP_GLOBAL_UNIVERSE_SYNC_MARKETS accepts comma-separated COUNTRY:EXCHANGE
pairs or the value ``all``. Markets not covered by the scheduled set are still
cached on demand whenever the app opens them.
"""
from __future__ import annotations

import os

from .country_packs import COUNTRY_PACKS, get_exchange
from .runtime import build_registry

_DEFAULT_TARGETS = (
    "US:NASDAQ",
    "US:NYSE",
    "GB:LSE",
    "NO:EURONEXT_OSLO",
    "SE:NASDAQ_STOCKHOLM",
    "JP:TSE_JP",
    "AU:ASX",
)


def _targets() -> list[tuple[str, str]]:
    raw = (os.environ.get("BIAP_GLOBAL_UNIVERSE_SYNC_MARKETS") or "").strip()
    if raw.lower() == "all":
        return [
            (country, exchange.code)
            for country, pack in COUNTRY_PACKS.items()
            for exchange in pack.exchanges
        ]
    entries = [part.strip() for part in raw.split(",") if part.strip()] if raw else list(_DEFAULT_TARGETS)
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if ":" not in entry:
            print(f"UNIVERSE_SYNC skip invalid target={entry!r}")
            continue
        country, exchange = (piece.strip().upper() for piece in entry.split(":", 1))
        try:
            spec = get_exchange(country, exchange)
        except Exception as exc:
            print(f"UNIVERSE_SYNC skip {country}:{exchange} invalid={exc}")
            continue
        key = (country, spec.code)
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def main() -> int:
    registry = build_registry()
    ok = 0
    failed = 0
    for country, exchange in _targets():
        try:
            provider = registry.universe(country, exchange)
            if hasattr(provider, "refresh"):
                rows = provider.refresh(country=country, exchange=exchange)
            else:
                rows = list(provider.list_instruments(country=country, exchange=exchange))
            if not rows:
                raise RuntimeError("provider returned no instruments; existing cache preserved")
            info = provider.snapshot_info(country=country, exchange=exchange) if hasattr(provider, "snapshot_info") else {}
            print(
                f"UNIVERSE_SYNC ok {country}:{exchange} count={len(rows)} "
                f"cached_at={info.get('fetchedAt') if isinstance(info, dict) else None}"
            )
            ok += 1
        except Exception as exc:
            # One market must never prevent the remaining countries from syncing.
            # PersistentUniverseProvider also refuses to overwrite a good cache
            # with an empty/failed refresh.
            print(f"UNIVERSE_SYNC failed {country}:{exchange} error={type(exc).__name__}:{str(exc)[:220]}")
            failed += 1
    print(f"UNIVERSE_SYNC complete ok={ok} failed={failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
