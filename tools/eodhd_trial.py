#!/usr/bin/env python3
"""One-off EODHD fundamentals completeness trial: N tickers per exchange from the staged ledgers. Needs BIAP_EODHD_FUNDAMENTALS=1 and a trial token.

Read-only (HTTP GET to EODHD, one request per ticker, paced). Writes a CSV. Buys nothing; with no token it exits with a clear message.
Usage: BIAP_EODHD_FUNDAMENTALS=1 BIAP_EODHD_API_TOKEN=... python tools/eodhd_trial.py --exchange DE:XETRA --exchange ES:BME_MADRID --n 20 --out trial.csv
"""
import argparse, csv, sys, time
sys.path.insert(0, "analysis")
from global_markets import eodhd_fundamentals as ef
from global_markets.analysis_ledger import AnalysisLedger


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--exchange", action="append", required=True); ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="eodhd_trial.csv"); ap.add_argument("--interval", type=float, default=1.0); a = ap.parse_args()
    if not ef.enabled():
        print("EODHD trial not run: set BIAP_EODHD_FUNDAMENTALS=1 and BIAP_EODHD_API_TOKEN (trial key). Nothing was requested.", file=sys.stderr); return 2
    rows = []
    for ex in a.exchange:
        country, name = ex.split(":"); led = AnalysisLedger(country, name)
        try:
            tickers = [r["ticker"] for r in led.summaries(limit=a.n)]
        finally:
            led.close()
        for t in tickers:
            try:
                c = ef.completeness_of(ef.fetch_fundamentals(t, name)); rows.append([ex, t, c["coveragePct"], c["coreComplete"], c["valuationComplete"], ";".join(c["missing"])])
            except Exception as exc:
                rows.append([ex, t, None, None, None, f"ERROR {str(exc)[:80]}"])
            time.sleep(a.interval)
    with open(a.out, "w", newline="") as f:
        csv.writer(f).writerows([["exchange", "ticker", "coveragePct", "coreComplete", "valuationComplete", "missing"], *rows])
    print(f"wrote {a.out}: {len(rows)} tickers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
