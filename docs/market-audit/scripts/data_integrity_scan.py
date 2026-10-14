#!/usr/bin/env python3
"""Read-only data-integrity scan over production analysis ledgers.

Usage: data_integrity_scan.py OUT.json MARKET_KEY [MARKET_KEY ...]   (e.g. DE__XETRA SE__NASDAQ_STOCKHOLM)

Checks every analysed in-universe row for violations that indicate extraction/normalisation defects
rather than investment evidence:
  ACCOUNTING_IDENTITY   |assets - liabilities - equity| > 2% of assets
  EQUITY_GT_ASSETS      equity > assets (or liabilities > assets*1.0001 with positive equity)
  CURRENT_GT_TOTAL      current assets > total assets, current liabilities > total liabilities
  MARGIN_IMPLAUSIBLE    |net_income / revenue| > 3  (units mixed between statements)
  ROA_IMPLAUSIBLE       |net_income / total_assets| > 1
  NEGATIVE_REVENUE      revenue < 0
  EBITDA_LT_EBIT        ebitda < operating_income (beyond 1%)
  CURRENCY_MISMATCH     reporting currency differs from listing currency (informational; per-share ratios are
                        suppressed by the pipeline in that case)
  NO_PERIOD             fundamentals present but filing_period_end missing
  STALE_PERIOD          filing_period_end older than 18 months (relative to the newest period in the market)
  DUP_ISIN              the same ISIN occurs more than once in the market (duplicate issuer)
  NO_ISIN               no ISIN on an equity row
Never writes to the ledgers; opens them with mode=ro.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

LEDGERS = Path("/var/lib/biap-global/analysis-ledger")


def load(key: str):
    db = sqlite3.connect(f"file:{LEDGERS / (key + '.sqlite3')}?mode=ro", uri=True)
    cols = [r[1] for r in db.execute("pragma table_info(ledger)")]
    q = "select ticker, result from ledger where in_universe=1 and status='COMPLETE' and result is not null"
    for ticker, blob in db.execute(q):
        try:
            payload = json.loads(zlib.decompress(blob))
        except Exception:  # noqa: BLE001 - corrupt blob is itself a finding
            yield ticker, None
            continue
        yield ticker, payload


def months_between(a: str, b: str) -> int:
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (yb - ya) * 12 + (mb - ma)


def scan(key: str) -> dict:
    rows = list(load(key))
    findings: dict[str, list] = defaultdict(list)
    isins: dict[str, list] = defaultdict(list)
    periods = [
        (p.get("company") or {}).get("filing_period_end") for _, p in rows if p
    ]
    periods = [x for x in periods if x]
    newest = max(periods) if periods else None
    with_fundamentals = 0
    for ticker, p in rows:
        if p is None:
            findings["CORRUPT_BLOB"].append(ticker)
            continue
        c = p.get("company") or {}
        n = lambda k: (float(c[k]) if c.get(k) is not None else None)  # noqa: E731
        a, l, e = n("total_assets"), n("total_liabilities"), n("total_equity")
        rev, ni, ebitda, ebit = n("revenue"), n("net_income"), n("ebitda"), n("operating_income")
        has_f = any(v is not None for v in (a, rev, ni, e))
        with_fundamentals += bool(has_f)
        isin = c.get("isin")
        if isin:
            isins[isin].append(ticker)
        else:
            findings["NO_ISIN"].append(ticker)
        if a and l is not None and e is not None and abs(a - l - e) > 0.02 * abs(a):
            findings["ACCOUNTING_IDENTITY"].append([ticker, a, l, e])
        if a and e is not None and e > a * 1.0001:
            findings["EQUITY_GT_ASSETS"].append([ticker, a, e])
        ca, cl = n("current_assets"), n("current_liabilities")
        if a and ca is not None and ca > a * 1.0001:
            findings["CURRENT_GT_TOTAL"].append([ticker, "current_assets", ca, a])
        if l and cl is not None and cl > l * 1.0001:
            findings["CURRENT_GT_TOTAL"].append([ticker, "current_liabilities", cl, l])
        if rev and ni is not None and abs(ni / rev) > 3:
            findings["MARGIN_IMPLAUSIBLE"].append([ticker, rev, ni])
        if a and ni is not None and abs(ni / a) > 1:
            findings["ROA_IMPLAUSIBLE"].append([ticker, a, ni])
        if rev is not None and rev < 0:
            findings["NEGATIVE_REVENUE"].append([ticker, rev])
        if ebitda is not None and ebit is not None and ebitda < ebit - 0.01 * abs(ebit):
            findings["EBITDA_LT_EBIT"].append([ticker, ebitda, ebit])
        cur, rcur = (c.get("currency") or "").upper(), (c.get("reporting_currency") or "").upper()
        if cur and rcur and cur != rcur and has_f:
            findings["CURRENCY_MISMATCH"].append([ticker, cur, rcur])
        per = c.get("filing_period_end")
        if has_f and not per:
            findings["NO_PERIOD"].append(ticker)
        if per and newest and months_between(per, newest) > 18:
            findings["STALE_PERIOD"].append([ticker, per])
    for isin, tickers in isins.items():
        if len(tickers) > 1:
            findings["DUP_ISIN"].append([isin, tickers])
    return {
        "market": key, "rows": len(rows), "withFundamentals": with_fundamentals, "newestPeriod": newest,
        "counts": {k: len(v) for k, v in findings.items()},
        "examples": {k: v[:12] for k, v in findings.items()},
    }


def main() -> int:
    out = Path(sys.argv[1])
    results = [scan(k) for k in sys.argv[2:]]
    out.write_text(json.dumps({"generatedAt": date.today().isoformat(), "results": results}, indent=1))
    for r in results:
        print(r["market"], r["rows"], "rows,", r["withFundamentals"], "with fundamentals;", dict(Counter(r["counts"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
