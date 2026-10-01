"""Pre-warm official national-OAM ESEF fundamentals for whole universes.

The Swedish OAM serves each ESEF package as one ~20-70 MB zip without HTTP
range support, so a cold first analysis can exceed the mobile request budget.
This job walks the complete authoritative SE/NO universes through the same
production fundamentals chain the app uses (registry -> persistent cache ->
OAM -> ESEF index -> vendor display fallback), so parsed official documents
and normalized snapshots already exist when a user opens a company.

It never changes trust: whatever the chain returns is cached exactly as the
app would cache it. Failures are isolated per instrument.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
import time

from .evidence_contract import official_fundamental_status
from .runtime import build_registry

MARKETS = (
    ("SE", "NASDAQ_STOCKHOLM"),
    ("NO", "EURONEXT_OSLO"),
    ("FR", "EURONEXT_PARIS"),
    ("ES", "BME_MADRID"),
)


def _one(provider, company):
    try:
        enriched = provider.enrich_fundamentals(company)
        status, detail = official_fundamental_status(enriched)
        return company.ticker, status, detail if status != "OFFICIAL_CURRENT" else enriched.filing_period_end
    except Exception as exc:  # isolation: one issuer never stops the job
        return company.ticker, "ERROR", f"{type(exc).__name__}: {str(exc)[:200]}"


def main() -> int:
    workers = max(1, int(os.environ.get("BIAP_OAM_WARM_WORKERS", "2")))
    limit = int(os.environ.get("BIAP_OAM_WARM_LIMIT", "0") or 0)
    only = {m.strip().upper() for m in (os.environ.get("BIAP_OAM_WARM_MARKETS") or "").split(",") if m.strip()}
    registry = build_registry()
    summary = {}
    for country, exchange in MARKETS:
        if only and country not in only:
            continue
        started = time.time()
        instruments = list(registry.universe(country, exchange).list_instruments(country=country, exchange=exchange))
        if limit:
            instruments = instruments[:limit]
        provider = registry.fundamentals(country, exchange)
        counts: Counter = Counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, provider, company) for company in instruments]
            for future in as_completed(futures):
                ticker, status, detail = future.result()
                counts[status] += 1
                print(json.dumps({"market": f"{country}/{exchange}", "ticker": ticker, "status": status, "detail": detail}, ensure_ascii=False), flush=True)
        summary[f"{country}/{exchange}"] = {"instruments": len(instruments), **counts, "seconds": round(time.time() - started)}
    print(json.dumps({"OAM_ESEF_WARM_SUMMARY": summary}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
