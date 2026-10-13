#!/usr/bin/env python3
"""Independent audit of BUY_CANDIDATE rows in an analysis-ledger snapshot.

For every BUY (evidence PASS) it
  1. re-reads the *raw* SEC companyfacts document from the BIAP source cache and re-extracts
     revenue / net income / assets / equity / operating cash flow for the reported period with
     its own tag list (NOT BIAP's normalizer), then compares to the ledger value;
  2. checks the gates a BUY must satisfy (official OFFICIAL_CURRENT source, evidence PASS,
     governance ACCEPT, mic/currency/country consistency, price date, core fields present);
  3. lists valuation gaps (P/E, peer P/E, fair value) as informational findings.

It never changes any data. Usage:
  audit_buy_candidates.py --ledger US__NASDAQ.sqlite3 --cache /var/lib/biap-global/cache/sec-edgar \
      --market US:NASDAQ:XNAS:USD --out docs/market-audit/us_nasdaq_buy_audit.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import zlib
from pathlib import Path
from typing import Any, Optional

# Independent, deliberately simple tag preference lists (US-GAAP, USD, annual 10-K facts).
TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    "total_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
}
TOLERANCE = 0.005  # 0.5 %
CORE = ("revenue", "net_income", "total_assets", "total_equity", "operating_cash_flow")


def cache_file(cache_dir: Path, url: str) -> Path:
    return cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")


def annual_value(facts: dict, tags: list[str], period_end: str) -> tuple[Optional[float], Optional[str]]:
    """First tag with an annual (>=350 day duration, or instant) USD fact ending on period_end."""
    from datetime import date

    usgaap = (facts.get("facts") or {}).get("us-gaap") or {}
    for tag in tags:
        rows = ((usgaap.get(tag) or {}).get("units") or {}).get("USD") or []
        best = None
        for row in rows:
            if row.get("end") != period_end:
                continue
            start = row.get("start")
            if start:
                days = (date.fromisoformat(period_end) - date.fromisoformat(start)).days
                if days < 350 or days > 380:
                    continue
            if str(row.get("form") or "").startswith("10-K") or str(row.get("form") or "").startswith("20-F") or str(row.get("form") or "").startswith("40-F"):
                if best is None or str(row.get("filed")) > str(best.get("filed")):
                    best = row
        if best is not None:
            return float(best["val"]), tag
    return None, None


def load_buys(ledger: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    out = []
    for (blob,) in conn.execute("SELECT result FROM ledger WHERE in_universe=1 AND call='BUY_CANDIDATE' AND evidence_status='PASS' AND result IS NOT NULL"):
        out.append(json.loads(zlib.decompress(blob).decode("utf-8")))
    return out


def audit_one(row: dict, cache_dir: Path, *, country: str, exchange: str, mic: str, currency: str) -> dict:
    findings: list[dict] = []

    def add(level: str, code: str, detail: str) -> None:
        findings.append({"level": level, "code": code, "detail": detail})

    fe = row.get("fundamentalEvidence") or {}
    values = fe.get("values") or {}
    company = row.get("company") or {}
    ev = row.get("evidence") or {}
    gov = row.get("governance") or {}

    # --- gates -------------------------------------------------------------------------
    if ev.get("status") != "PASS":
        add("FAIL", "evidence_not_pass", str(ev.get("status")))
    if fe.get("officialStatus") != "OFFICIAL_CURRENT" or fe.get("isOfficial") is not True:
        add("FAIL", "fundamentals_not_official_current", f"{fe.get('officialStatus')} isOfficial={fe.get('isOfficial')}")
    if gov.get("final_call") != "BUY_CANDIDATE" or not gov.get("accepted") or gov.get("abstained"):
        add("FAIL", "governance_not_accepted", json.dumps({k: gov.get(k) for k in ("action", "final_call", "accepted", "abstained")}))
    if row.get("country") != country or row.get("exchange") != exchange:
        add("FAIL", "market_identifier_mismatch", f"{row.get('country')}:{row.get('exchange')}")
    if row.get("mic") != mic:
        add("FAIL", "mic_mismatch", str(row.get("mic")))
    if row.get("currency") != currency or fe.get("values", {}).get("reporting_currency") not in (currency, None):
        add("WARN", "currency", f"quote={row.get('currency')} reporting={values.get('reporting_currency')}")
    if not company.get("price") or not company.get("price_observed_at"):
        add("FAIL", "missing_price", "no price/timestamp")
    for key in CORE:
        if values.get(key) in (None, 0):
            add("FAIL", f"missing_core_{key}", "BUY without core fundamental")
    if float(row.get("confidence") or 0) < 0.55:
        add("FAIL", "confidence_below_buy_floor", str(row.get("confidence")))
    if float(row.get("score") or 0) <= 0:
        add("FAIL", "non_positive_score", str(row.get("score")))

    # --- independent re-extraction -------------------------------------------------------
    verification: dict[str, Any] = {}
    url = fe.get("sourceUrl")
    period = fe.get("reportPeriod")
    cached = cache_file(cache_dir, url) if url else None
    if not cached or not cached.exists():
        add("WARN", "raw_source_not_cached", f"{url}")
    else:
        raw = json.loads(cached.read_text())
        facts = raw.get("payload") or raw
        for field, tags in TAGS.items():
            mine, tag = annual_value(facts, tags, str(period))
            theirs = values.get(field)
            if mine is None:
                verification[field] = {"status": "NOT_INDEPENDENTLY_FOUND", "ledger": theirs}
                if theirs not in (None, 0):
                    add("WARN", f"unverified_{field}", f"ledger={theirs} but none of {tags} has an annual USD fact for {period}")
                continue
            if theirs in (None, 0):
                verification[field] = {"status": "LEDGER_MISSING", "independent": mine, "tag": tag}
                continue
            rel = abs(mine - float(theirs)) / max(abs(mine), 1.0)
            verification[field] = {"status": "MATCH" if rel <= TOLERANCE else "MISMATCH", "ledger": theirs, "independent": mine, "tag": tag, "relDiff": round(rel, 6)}
            if rel > TOLERANCE:
                add("FAIL", f"mismatch_{field}", f"ledger={theirs} independent={mine} ({tag}) rel={rel:.4f}")

    # --- internal consistency -----------------------------------------------------------
    rev, ni = values.get("revenue"), values.get("net_income")
    if rev and ni is not None and values.get("net_margin_pct") is not None:
        calc = 100.0 * ni / rev
        if abs(calc - float(values["net_margin_pct"])) > 0.05:
            add("FAIL", "net_margin_inconsistent", f"calc={calc:.3f} stored={values['net_margin_pct']}")

    # --- valuation completeness (informational) ------------------------------------------
    gaps = [name for name in ("pe", "sector_pe", "pb", "ev_ebitda") if company.get(name) in (None, 0)]
    if gaps:
        add("INFO", "valuation_gaps", ",".join(gaps))
    if not any(key for key in row if "fair" in key.lower()) and "fair_value" not in company:
        add("INFO", "no_fair_value_estimate", "no fair-value output exists in the schema; none is fabricated")

    verdict = "FAIL" if any(f["level"] == "FAIL" for f in findings) else "WARN" if any(f["level"] == "WARN" for f in findings) else "PASS"
    return {
        "ticker": row.get("ticker"), "name": row.get("name"), "score": row.get("score"), "confidence": row.get("confidence"),
        "rankScore": round(float(row.get("score") or 0) * float(row.get("confidence") or 0), 6),
        "reportPeriod": period, "priceObservedAt": company.get("price_observed_at"),
        "verdict": verdict, "findings": findings, "verification": verification,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--market", required=True, help="COUNTRY:EXCHANGE:MIC:CCY")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    country, exchange, mic, ccy = args.market.split(":")
    rows = load_buys(Path(args.ledger))
    results = [audit_one(r, Path(args.cache), country=country, exchange=exchange, mic=mic, currency=ccy) for r in rows]
    results.sort(key=lambda r: r["rankScore"], reverse=True)
    summary = {k: sum(1 for r in results if r["verdict"] == k) for k in ("PASS", "WARN", "FAIL")}
    Path(args.out).write_text(json.dumps({"market": args.market, "buyCount": len(results), "summary": summary, "results": results}, indent=1))
    print(json.dumps({"buyCount": len(results), **summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
