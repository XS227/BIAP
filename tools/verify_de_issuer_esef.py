#!/usr/bin/env python3
"""Verify candidate issuer-hosted ESEF packages for German issuers.

Input: a JSON object {isin: {"ticker", "lei", "candidates": [[url, score], ...], "site"}}
(produced by an issuer-website discovery crawl). Each candidate is downloaded
with the same size/format guards BIAP uses in production and parsed with the
shared ESEF extractor. A candidate is accepted only if the report carries
inline XBRL, its embedded entity identifiers include the issuer's LEI and it
contains annual IFRS duration facts (so HGB single-entity reports and PDF
bundles are rejected). Per issuer the newest accepted period wins.

Usage:
  BIAP_GLOBAL_DATA_DIR=/tmp/x python tools/verify_de_issuer_esef.py candidates.json out.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from global_markets.ixbrl import annual_period_end  # noqa: E402
from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling  # noqa: E402
from global_markets.providers import GlobalProviderError  # noqa: E402

IFRS_FLOWS = ("ifrs-full:ProfitLoss", "ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers")


def verify(provider: NationalOAMESEFProvider, isin: str, lei: str, url: str) -> dict:
    filing = OAMFiling(oam="de-issuer", document_id=f"verify:{url}", package_url=url, landing_url=url)
    try:
        package = provider.package_facts(filing)
    except (GlobalProviderError, OSError, ValueError, KeyError) as exc:
        return {"url": url, "ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    except Exception as exc:  # zip/parse errors from arbitrary web files
        return {"url": url, "ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    entities = {e.upper() for e in package.get("entities") or []}
    if not entities:
        return {"url": url, "ok": False, "reason": "no inline XBRL"}
    if lei.upper() not in entities:
        return {"url": url, "ok": False, "reason": f"entity {sorted(entities)} != {lei}"}
    period = annual_period_end(package.get("facts") or [], IFRS_FLOWS)
    if not period:
        return {"url": url, "ok": False, "reason": "no annual IFRS duration facts (HGB/separate report?)"}
    return {"url": url, "ok": True, "period_end": period, "facts": package.get("factCount")}


def main() -> int:
    candidates = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out_path = Path(sys.argv[2])
    results = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    provider = NationalOAMESEFProvider(timeout=90.0, locators=[])
    for isin, row in candidates.items():
        if isin in results or not row.get("lei"):
            continue
        urls = [u for u, _ in row.get("candidates") or [] if urlparse(u).scheme == "https"]
        checks = [verify(provider, isin, row["lei"], url) for url in urls[:6]]
        accepted = sorted((c for c in checks if c["ok"]), key=lambda c: c["period_end"], reverse=True)
        results[isin] = {
            "ticker": row.get("ticker"), "lei": row["lei"], "site": row.get("site"),
            "checks": checks, "accepted": accepted[0] if accepted else None,
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        best = results[isin]["accepted"]
        print(row.get("ticker"), best["period_end"] if best else "-", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
