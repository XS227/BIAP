#!/usr/bin/env python3
"""Sample every configured BIAP Global exchange for fundamentals freshness.

This is a production diagnostic, not a ranking job. It resolves a small number
of ordinary equities per exchange and records filing period, source trust,
Evidence status, and explicit stale-fundamentals blocks. It never fabricates
missing fields and it does not place orders.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
import os
import urllib.parse
import urllib.request

BASE = os.environ.get("BIAP_GLOBAL_PUBLIC_API", "https://biap.dadashi.no/global-api/global").rstrip("/")
MAX_WORKERS = int(os.environ.get("BIAP_FRESHNESS_AUDIT_WORKERS", "6"))
CANDIDATES_PER_EXCHANGE = int(os.environ.get("BIAP_FRESHNESS_AUDIT_CANDIDATES", "3"))


def get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "BIAP freshness audit"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, body: dict, timeout: int = 90):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "BIAP freshness audit"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def age_days(period: str | None):
    text = str(period or "")[:10]
    if not text:
        return None
    try:
        return (date.today() - date.fromisoformat(text)).days
    except ValueError:
        return None


def audit_exchange(country: str, exchange: str):
    row = {"country": country, "exchange": exchange}
    try:
        catalog = get_json(f"{BASE}/instruments/{country}/{urllib.parse.quote(exchange)}?limit={CANDIDATES_PER_EXCHANGE}&offset=0", 45)
        items = catalog.get("instruments") or []
        row["catalogCount"] = len(items)
        if not items:
            row["status"] = "NO_INSTRUMENTS"
            return row

        attempts = []
        for item in items[:CANDIDATES_PER_EXCHANGE]:
            try:
                payload = post_json(f"{BASE}/analyze", {
                    "country": country,
                    "exchange": exchange,
                    "ticker": item.get("ticker"),
                    "name": item.get("name"),
                    "currency": item.get("currency"),
                    "isin": item.get("isin"),
                    "lei": item.get("lei"),
                }, 90)
            except Exception as exc:
                attempts.append({"ticker": item.get("ticker"), "error": f"{type(exc).__name__}: {exc}"})
                continue
            company = payload.get("company") or {}
            evidence = payload.get("evidence") or {}
            raw = company.get("raw_provider_fields") or {}
            sources = company.get("sources") or []
            period = company.get("filing_period_end")
            attempts.append({
                "ticker": payload.get("ticker") or item.get("ticker"),
                "filingPeriodEnd": period,
                "fundamentalAgeDays": age_days(period),
                "evidenceStatus": evidence.get("status"),
                "missingCritical": evidence.get("missing_critical") or [],
                "fundamentalsStatus": (payload.get("providerDiagnostics") or {}).get("fundamentalsStatus"),
                "primaryStale": bool(raw.get("fundamentals_primary_stale")),
                "primaryPeriod": raw.get("fundamentals_primary_period"),
                "fallbackPeriod": raw.get("fundamentals_fallback_period"),
                "sourceTypes": sorted({str(s.get("source_type") or "") for s in sources if isinstance(s, dict)}),
            })
            # One successful live analysis is sufficient as a representative
            # exchange-level smoke sample.
            break

        row["attempts"] = attempts
        good = next((x for x in attempts if "error" not in x), None)
        if not good:
            row["status"] = "ANALYSIS_ERROR"
        elif "fresh_fundamentals" in (good.get("missingCritical") or []):
            row["status"] = "STALE_FUNDAMENTALS"
        elif good.get("filingPeriodEnd") is None:
            row["status"] = "NO_FILING_PERIOD"
        elif "fundamental_source" in (good.get("missingCritical") or []):
            row["status"] = "UNVERIFIED_FUNDAMENTALS"
        else:
            row["status"] = "OK"
        return row
    except Exception as exc:
        row["status"] = "ERROR"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row


def main():
    countries = get_json(f"{BASE}/countries", 30).get("countries") or []
    targets = []
    for country in countries:
        if country.get("enabled") is False:
            continue
        code = str(country.get("country") or "").upper()
        # Iran/Japan are intentionally left untouched in the current project
        # plan; audit them only when explicitly re-enabled.
        if code in {"IR", "JP"}:
            continue
        for exchange in country.get("exchanges") or []:
            ex = str(exchange.get("code") or "")
            if code and ex:
                targets.append((code, ex))

    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(audit_exchange, c, e): (c, e) for c, e in targets}
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda x: (x.get("country", ""), x.get("exchange", "")))
    summary = {
        "exchangesAudited": len(rows),
        "ok": sum(r.get("status") == "OK" for r in rows),
        "staleFundamentals": sum(r.get("status") == "STALE_FUNDAMENTALS" for r in rows),
        "unverifiedFundamentals": sum(r.get("status") == "UNVERIFIED_FUNDAMENTALS" for r in rows),
        "noFilingPeriod": sum(r.get("status") == "NO_FILING_PERIOD" for r in rows),
        "errors": sum(r.get("status") in {"ERROR", "ANALYSIS_ERROR"} for r in rows),
    }
    print("SUMMARY", json.dumps(summary, sort_keys=True))
    for row in rows:
        print("MARKET", json.dumps(row, sort_keys=True))
    with open("global-fundamentals-freshness-audit.json", "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "markets": rows}, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
