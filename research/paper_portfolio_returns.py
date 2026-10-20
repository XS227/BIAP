#!/usr/bin/env python3
"""1-month (or any horizon) returns of the frozen paper portfolio: BUY vs SELL vs each market's benchmark index.

Usage: python research/paper_portfolio_returns.py research/paper_portfolio_2026-10-20.json [--end 2026-11-20] [--json out.json]

* Entry = the vendor's final daily close on snapshotDate, re-read now; the snapshot's ``entryClose`` is used only when the vendor no longer
  returns that day. Rows whose re-read differs from the stored value by more than 2% are counted in the output.
  (Stored value: vendor close on snapshotDate.) Exit = last vendor close on or before ``--end``
  (default: snapshotDate + 31 days). Same source and units for both legs, so pence/pound scale and splits cancel out.
  Closes are vendor-adjusted-close-free ``close`` (split-adjusted, no dividends): returns are price returns.
* Rows without an entry close, or without any close in the window, are listed as missing and excluded - never filled.
* Weights are the snapshot's equal weights within each exchange and side, renormalised over rows that have data.
* Benchmark = price index named in ``markets[...].benchmark``, same entry date / exit rule.
* The pooled "ALL" rows weight each exchange equally (not each stock).
Reads the snapshot only; never modifies it.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def closes(symbol: str, start: date, end: date) -> dict[str, float]:
    """{YYYY-MM-DD: close} for vendor symbol between start-7d and end+1d."""
    p1 = int(datetime.combine(start - timedelta(days=7), datetime.min.time(), timezone.utc).timestamp())
    p2 = int(datetime.combine(end + timedelta(days=2), datetime.min.time(), timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?period1={p1}&period2={p2}&interval=1d"
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.load(resp)["chart"]["result"][0]
            off = result["meta"].get("gmtoffset") or 0
            return {datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(): float(c)
                    for t, c in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]) if c is not None}
        except Exception:                                 # noqa: BLE001
            continue
    return {}


def leg_return(series: dict[str, float], entry_date: str, entry: float | None, end: date) -> tuple[float | None, str | None, str]:
    if entry is None or entry <= 0:
        return None, None, "no entry close"
    window = sorted(d for d in series if entry_date < d <= end.isoformat())
    if not window:
        return None, None, "no close after entry"
    return series[window[-1]] / entry - 1.0, window[-1], ""


def weighted(pairs: list[tuple[float, float]]) -> float | None:
    total = sum(w for w, _ in pairs)
    return sum(w * r for w, r in pairs) / total if total else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--end")
    ap.add_argument("--json")
    args = ap.parse_args()
    snap = json.loads(Path(args.snapshot).read_text())
    start = date.fromisoformat(snap["snapshotDate"])
    end = date.fromisoformat(args.end) if args.end else start + timedelta(days=31)
    if end > datetime.now(timezone.utc).date():
        print(f"warning: end {end} is in the future; returns use the latest available close", file=sys.stderr)
    rows = snap["holdings"]

    symbols = sorted({r["vendorSymbol"] for r in rows if r.get("vendorSymbol")})
    with ThreadPoolExecutor(max_workers=4) as pool:
        series = dict(zip(symbols, pool.map(lambda s: closes(s, start, end), symbols)))
    bench = {m["benchmark"] for m in snap["markets"].values() if isinstance(m, dict) and m.get("benchmark")}
    bseries = {b: closes(b, start, end) for b in sorted(bench)}

    per_market, missing, entry_drift = {}, [], []
    for key, mk in snap["markets"].items():
        if not isinstance(mk, dict) or "benchmark" not in mk:
            continue
        b = bseries.get(mk["benchmark"], {})
        entry_b = b.get(snap["snapshotDate"])
        bret, bdate, why = leg_return(b, snap["snapshotDate"], entry_b, end)
        out = {"benchmark": mk["benchmark"], "benchmarkReturn": bret, "benchmarkExitDate": bdate, "benchmarkNote": why or None}
        for side in ("BUY", "SELL"):
            mine = [r for r in rows if r["market"] == key and r["side"] == side]
            pairs, rets = [], []
            for r in mine:
                sr = series.get(r.get("vendorSymbol"), {})
                entry = sr.get(snap["snapshotDate"]) or r.get("entryClose")
                if r.get("entryClose") and sr.get(snap["snapshotDate"]) and abs(sr[snap["snapshotDate"]] / r["entryClose"] - 1) > 0.02:
                    entry_drift.append(r["ticker"])
                ret, exit_day, why = leg_return(sr, snap["snapshotDate"], entry, end)
                if ret is None:
                    missing.append({"market": key, "side": side, "ticker": r["ticker"], "reason": why})
                    continue
                pairs.append((r["weight"], ret)); rets.append(ret)
            r_ = weighted(pairs)
            out[side] = {"holdings": len(mine), "withData": len(pairs), "equalWeightReturn": r_,
                         "medianReturn": statistics.median(rets) if rets else None,
                         "excessVsBenchmark": None if r_ is None or bret is None else r_ - bret,
                         "hitRateVsBenchmark": None if not rets or bret is None else sum(1 for x in rets if x > bret) / len(rets)}
        buy, sell = out["BUY"]["equalWeightReturn"], out["SELL"]["equalWeightReturn"]
        out["BUY_minus_SELL"] = None if buy is None or sell is None else buy - sell
        per_market[key] = out

    def pooled(field):
        vals = [m[field] if field in ("benchmarkReturn", "BUY_minus_SELL") else m[field[0]][field[1]] for m in per_market.values()]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    summary = {"BUY": pooled(("BUY", "equalWeightReturn")), "SELL": pooled(("SELL", "equalWeightReturn")),
               "benchmark": pooled("benchmarkReturn"), "BUY_minus_SELL": pooled("BUY_minus_SELL"),
               "BUY_excess": pooled(("BUY", "excessVsBenchmark")), "SELL_excess": pooled(("SELL", "excessVsBenchmark"))}
    report = {"snapshot": snap["snapshotDate"], "end": end.isoformat(), "markets": per_market, "ALL_exchange_equal_weighted": summary,
              "missing": missing, "entryDriftOver2pct": entry_drift}
    pct = lambda v: "   n/a " if v is None else f"{v*100:+7.2f}%"
    print(f"Paper portfolio {snap['snapshotDate']} -> {end}  (price returns, equal weight; ALL = exchanges equally weighted)")
    print(f"{'market':<26}{'BUY n':>7}{'BUY':>9}{'SELL n':>8}{'SELL':>9}{'bench':>9}{'BUY-bm':>9}{'SELL-bm':>9}{'BUY-SELL':>10}")
    for key, m in per_market.items():
        print(f"{key:<26}{m['BUY']['withData']:>3}/{m['BUY']['holdings']:<3}{pct(m['BUY']['equalWeightReturn'])}"
              f"{m['SELL']['withData']:>4}/{m['SELL']['holdings']:<3}{pct(m['SELL']['equalWeightReturn'])}{pct(m['benchmarkReturn'])}"
              f"{pct(m['BUY']['excessVsBenchmark'])}{pct(m['SELL']['excessVsBenchmark'])}{pct(m['BUY_minus_SELL'])}")
    print(f"{'ALL':<26}{'':>7}{pct(summary['BUY'])}{'':>8}{pct(summary['SELL'])}{pct(summary['benchmark'])}"
          f"{pct(summary['BUY_excess'])}{pct(summary['SELL_excess'])}{pct(summary['BUY_minus_SELL'])}")
    print(f"missing/excluded rows: {len(missing)}; entry close re-read differs >2% from stored: {len(entry_drift)}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
