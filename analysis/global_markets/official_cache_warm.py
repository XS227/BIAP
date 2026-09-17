"""Warm a bounded BIAP Global resilience baseline on the server.

This is deliberately *not* a stock-picking list. Targets are liquid benchmark
constituents used only as cross-market source/adapter probes so the server starts
with a useful verified cache before a user opens a company. Every other company
is cached on demand after its first analysis.

Failures are isolated per symbol. A regulator/provider outage never deletes an
existing snapshot.
"""
from __future__ import annotations

import json
import os
from typing import Iterable

from .runtime import build_registry


# Coverage probes spanning both US venues, the ESEF/UKSEF countries and KAP.
# Symbols that change/delist simply log a miss; the daily job continues safely.
_DEFAULT_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("US", "NASDAQ", "AAPL"), ("US", "NASDAQ", "MSFT"),
    ("US", "NASDAQ", "NVDA"), ("US", "NASDAQ", "AMZN"),
    ("US", "NASDAQ", "GOOGL"), ("US", "NASDAQ", "META"),
    ("US", "NYSE", "JPM"), ("US", "NYSE", "XOM"),
    ("US", "NYSE", "JNJ"),
    ("GB", "LSE", "AZN"), ("GB", "LSE", "SHEL"), ("GB", "LSE", "HSBA"),
    ("DE", "XETRA", "SAP"), ("DE", "XETRA", "SIE"), ("DE", "XETRA", "ALV"),
    ("FR", "EURONEXT_PARIS", "MC"), ("FR", "EURONEXT_PARIS", "OR"),
    ("NL", "EURONEXT_AMSTERDAM", "ASML"), ("NL", "EURONEXT_AMSTERDAM", "INGA"),
    ("ES", "BME_MADRID", "SAN"), ("ES", "BME_MADRID", "ITX"),
    ("IT", "EURONEXT_MILAN", "ENI"), ("IT", "EURONEXT_MILAN", "ENEL"),
    ("SE", "NASDAQ_STOCKHOLM", "VOLV-B"), ("SE", "NASDAQ_STOCKHOLM", "ERIC-B"),
    ("NO", "EURONEXT_OSLO", "EQNR"), ("NO", "EURONEXT_OSLO", "DNB"),
    ("DK", "NASDAQ_COPENHAGEN", "NOVO-B"),
    ("FI", "NASDAQ_HELSINKI", "NOKIA"),
    ("BE", "EURONEXT_BRUSSELS", "ABI"),
    ("IE", "EURONEXT_DUBLIN", "AIBG"),
    ("PT", "EURONEXT_LISBON", "EDP"),
    ("IS", "NASDAQ_ICELAND", "ARION"),
    ("TR", "BIST", "AKBNK"), ("TR", "BIST", "GARAN"),
    ("TR", "BIST", "THYAO"), ("TR", "BIST", "ASELS"),
    ("TR", "BIST", "KCHOL"), ("TR", "BIST", "BIMAS"),
)


def _targets() -> Iterable[tuple[str, str, str]]:
    raw = (os.environ.get("BIAP_GLOBAL_CACHE_WARM_TARGETS") or "").strip()
    if not raw:
        return _DEFAULT_TARGETS
    result: list[tuple[str, str, str]] = []
    for item in raw.split(","):
        parts = [part.strip().upper() for part in item.split(":")]
        if len(parts) == 3 and all(parts):
            result.append((parts[0], parts[1], parts[2]))
    return tuple(result) or _DEFAULT_TARGETS


def _exact(provider, country: str, exchange: str, ticker: str):
    search = getattr(provider, "search_instruments", None)
    rows = list(search(country=country, exchange=exchange, query=ticker, limit=20)) if callable(search) else []
    return next((row for row in rows if row.ticker.strip().upper() == ticker.upper()), None)


def main() -> int:
    registry = build_registry()
    warm_market = (os.environ.get("BIAP_GLOBAL_CACHE_WARM_MARKET", "true").strip().lower() == "true")
    summary = {"targets": 0, "resolved": 0, "marketOk": 0, "fundamentalsOk": 0, "officialOk": 0, "failures": []}

    for country, exchange, ticker in _targets():
        summary["targets"] += 1
        try:
            seed = _exact(registry.universe(country, exchange), country, exchange, ticker)
            if seed is None:
                raise RuntimeError("exact instrument not found")
            summary["resolved"] += 1
        except Exception as exc:
            summary["failures"].append(f"{country}/{exchange}/{ticker}:resolve:{type(exc).__name__}")
            continue

        enriched = seed
        if warm_market:
            try:
                enriched = registry.market(country, exchange).enrich_market(enriched)
                summary["marketOk"] += 1
            except Exception as exc:
                summary["failures"].append(f"{country}/{exchange}/{ticker}:market:{type(exc).__name__}")

        try:
            enriched = registry.fundamentals(country, exchange).enrich_fundamentals(enriched)
            summary["fundamentalsOk"] += 1
            official = False
            for source in enriched.sources:
                kind = source.source_type.lower().replace("-", "_")
                if "vendor" not in kind and any(token in kind for token in ("official", "regulatory", "xbrl", "filing")):
                    official = True
                    break
            if official:
                summary["officialOk"] += 1
        except Exception as exc:
            summary["failures"].append(f"{country}/{exchange}/{ticker}:fundamentals:{type(exc).__name__}")

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    # This is a best-effort warming job; existing data must remain usable even
    # when one or more external providers are down.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
