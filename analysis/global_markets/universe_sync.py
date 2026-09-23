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

# Keep the principal supported global venues warm so switching country in the
# app does not depend on a fresh upstream catalog request. Failures are isolated
# per market and an existing verified cache is never replaced by an empty result.
_DEFAULT_TARGETS = (
    "US:NASDAQ",
    "US:NYSE",
    "GB:LSE",
    "NO:EURONEXT_OSLO",
    "SE:NASDAQ_STOCKHOLM",
    "DK:NASDAQ_COPENHAGEN",
    "FI:NASDAQ_HELSINKI",
    "IS:NASDAQ_ICELAND",
    "NL:EURONEXT_AMSTERDAM",
    "FR:EURONEXT_PARIS",
    "BE:EURONEXT_BRUSSELS",
    "IE:EURONEXT_DUBLIN",
    "PT:EURONEXT_LISBON",
    "IT:EURONEXT_MILAN",
    "DE:XETRA",
    "DE:FRANKFURT",
    "ES:BME_MADRID",
    "CH:SIX",
    "AU:ASX",
    "NZ:NZX",
    "JP:TSE_JP",
    "CA:TSX",
    "CA:TSXV",
    "HK:HKEX",
    "SG:SGX",
    "IN:NSE",
    "IN:BSE",
    "SA:SAUDI_EXCHANGE",
    "TR:BIST",
    "ZA:JSE",
    "BR:B3",
    "KR:KRX",
    "AE:ADX",
    "AE:DFM",
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
            upstream = getattr(provider, "upstream", provider)
            upstream_id = str(getattr(upstream, "provider_id", ""))
            if upstream_id == "official-esma-firds-universe" and hasattr(provider, "snapshot_info"):
                existing = provider.snapshot_info(country=country, exchange=exchange)
                if isinstance(existing, dict) and existing.get("available") and existing.get("fresh"):
                    print(
                        f"UNIVERSE_SYNC skip-fresh {country}:{exchange} "
                        f"official={existing.get('officialCount')} resolved={existing.get('resolvedCount')} "
                        f"coverage={existing.get('resolutionCoveragePct')}%"
                    )
                    ok += 1
                    continue
            if hasattr(provider, "refresh"):
                rows = provider.refresh(country=country, exchange=exchange)
            else:
                rows = list(provider.list_instruments(country=country, exchange=exchange))
            if not rows:
                raise RuntimeError("provider returned no instruments; existing cache preserved")
            info = provider.snapshot_info(country=country, exchange=exchange) if hasattr(provider, "snapshot_info") else {}
            print(
                f"UNIVERSE_SYNC ok {country}:{exchange} count={len(rows)} "
                f"official={info.get('officialCount') if isinstance(info, dict) else None} "
                f"resolved={info.get('resolvedCount') if isinstance(info, dict) else None} "
                f"coverage={info.get('resolutionCoveragePct') if isinstance(info, dict) else None}% "
                f"cached_at={info.get('fetchedAt') if isinstance(info, dict) else None}"
            )
            ok += 1
        except Exception as exc:
            print(f"UNIVERSE_SYNC failed {country}:{exchange} error={type(exc).__name__}:{str(exc)[:220]}")
            failed += 1
    print(f"UNIVERSE_SYNC complete ok={ok} failed={failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
