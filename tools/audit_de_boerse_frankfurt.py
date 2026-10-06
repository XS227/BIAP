#!/usr/bin/env python3
"""Audit Börse Frankfurt official key-data coverage for the live DE universe."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from global_markets.boerse_frankfurt_fundamentals import (  # noqa: E402
    BoerseFrankfurtFundamentalsProvider,
)
from global_markets.models import GlobalCompany  # noqa: E402


CATALOG_BASE = "https://biap.dadashi.no/global-api/global/instruments/DE"


def catalog(exchange: str) -> list[dict]:
    with urlopen(f"{CATALOG_BASE}/{exchange}?limit=1000", timeout=60) as response:
        payload = json.load(response)
    return [row for row in payload.get("instruments") or [] if isinstance(row, dict)]


def audit_one(row: dict) -> dict:
    company = GlobalCompany(
        country="DE",
        exchange=str(row.get("exchange") or "FRANKFURT"),
        mic_code=row.get("mic_code"),
        currency=str(row.get("currency") or "EUR"),
        ticker=str(row.get("ticker") or ""),
        name=str(row.get("name") or row.get("ticker") or ""),
        isin=row.get("isin"),
        lei=row.get("lei"),
    )
    provider = BoerseFrankfurtFundamentalsProvider(timeout=15.0, limit=4)
    try:
        enriched = provider.enrich_fundamentals(company)
    except Exception as exc:
        return {
            "ticker": company.ticker,
            "isin": company.isin,
            "exchange": company.exchange,
            "status": "error",
            "error": f"{type(exc).__name__}: {str(exc)[:220]}",
        }
    raw = enriched.raw_provider_fields or {}
    core = {
        "revenue": enriched.revenue,
        "net_income": enriched.net_income,
        "assets": enriched.total_assets,
        "liabilities": enriched.total_liabilities,
        "equity": enriched.total_equity,
        "current_assets": enriched.current_assets,
        "current_liabilities": enriched.current_liabilities,
    }
    return {
        "ticker": company.ticker,
        "isin": company.isin,
        "exchange": company.exchange,
        "status": "ok",
        "year": raw.get("de_bf_report_year"),
        "coreAvailable": sum(value is not None for value in core.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    rows_by_isin: dict[str, dict] = {}
    for exchange in ("FRANKFURT", "XETRA"):
        for row in catalog(exchange):
            isin = str(row.get("isin") or "").upper().strip()
            if not isin.startswith("DE"):
                continue
            rows_by_isin.setdefault(isin, row)

    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(12, args.workers))) as pool:
        futures = [pool.submit(audit_one, row) for row in rows_by_isin.values()]
        for future in as_completed(futures):
            results.append(future.result())

    status = Counter(row["status"] for row in results)
    years = Counter(str(row.get("year")) for row in results if row["status"] == "ok")
    core = Counter(
        str(row.get("coreAvailable"))
        for row in results
        if row["status"] == "ok"
    )
    errors = Counter(
        (row.get("error") or "").split(":", 1)[0]
        for row in results
        if row["status"] == "error"
    )

    summary = {
        "uniqueGermanISINs": len(rows_by_isin),
        "status": dict(status),
        "years": dict(years),
        "coreAvailable": dict(core),
        "errorTypes": dict(errors),
    }
    print("DE_BF_AUDIT=" + json.dumps(summary, sort_keys=True))

    for row in sorted(results, key=lambda x: (x["status"], x["ticker"])):
        if row["status"] == "error":
            print("ERROR=" + json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
