#!/usr/bin/env python3
"""1-month (or any horizon) returns of the frozen paper portfolio: BUY vs SELL vs each market's benchmark index.

Usage: python research/paper_portfolio_returns.py research/paper_portfolio_2026-10-20.json [--end 2026-11-20] [--json out.json]

* Entry = the vendor's final daily close on snapshotDate, re-read now; the snapshot's ``entryClose`` is used only when the vendor no longer
  returns that day. Rows whose re-read differs from the stored value by more than 2% are counted in the output.
  (Stored value: vendor close on snapshotDate.) Exit = last vendor close on or before ``--end``
  (default: snapshotDate + 31 days). Same source and units for both legs, so pence/pound scale and splits cancel out.
  Closes are vendor-adjusted-close-free ``close`` (split-adjusted, no dividends): returns are price returns.
* Holdings the snapshot has no entry close for may be filled from the separate entry supplement
  (``<snapshot>_entry_supplement.json`` next to it, or ``--supplement``); it is only accepted if its ``snapshotSha256`` matches the
  snapshot file, and only its exact snapshot-date closes are used. Report lines show how many entries came from it.
* Report groups: (A) all decisions, priced or not, for decision-behaviour statistics; (B) the priced subset, for returns;
  (C) every holding not in (B), listed with its reason (no entry price / no exit price). priced + unpriced always equals the
  number of decisions (asserted). Excluded rows are never filled and never dropped silently.
* Weights are the snapshot's equal weights within each exchange and side, renormalised over rows that have data.
* Benchmark = price index named in ``markets[...].benchmark``, same entry date / exit rule.
* The pooled "ALL" rows weight each exchange equally (not each stock).
Reads the snapshot only; never modifies it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
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
    ap.add_argument("--supplement")
    args = ap.parse_args()
    raw = Path(args.snapshot).read_bytes()
    snap = json.loads(raw)
    sup_path = Path(args.supplement) if args.supplement else Path(args.snapshot).with_name(Path(args.snapshot).stem + "_entry_supplement.json")
    fills = {}
    if sup_path.exists():
        sup = json.loads(sup_path.read_text())
        if sup.get("snapshotSha256") != hashlib.sha256(raw).hexdigest():
            sys.exit(f"{sup_path.name} was built for a different snapshot file (sha256 mismatch)")
        fills = {(f["market"], f["ticker"], f["side"]): f for f in sup["fills"] if f.get("close") is not None and f.get("closeDate") == snap["snapshotDate"]}
    start = date.fromisoformat(snap["snapshotDate"])
    end = date.fromisoformat(args.end) if args.end else start + timedelta(days=31)
    if end > datetime.now(timezone.utc).date():
        print(f"warning: end {end} is in the future; returns use the latest available close", file=sys.stderr)
    rows = snap["holdings"]

    def fill_of(r):
        return fills.get((r["market"], r["ticker"], r["side"])) if r.get("entryClose") is None else None

    sup_by_key = {(f["market"], f["ticker"], f["side"]): f for f in (sup["fills"] if fills or sup_path.exists() else [])} if sup_path.exists() else {}
    for r in rows:                      # in-memory view only; the snapshot file is never written
        r["_snapshotHadEntry"] = r.get("entryClose") is not None
        f = fill_of(r)
        if f:
            r["vendorSymbol"], r["entryClose"], r["fromSupplement"] = f["vendorSymbol"], f["close"], True
    symbols = sorted({r["vendorSymbol"] for r in rows if r.get("vendorSymbol")})
    with ThreadPoolExecutor(max_workers=4) as pool:
        series = dict(zip(symbols, pool.map(lambda s: closes(s, start, end), symbols)))
    bench = {m["benchmark"] for m in snap["markets"].values() if isinstance(m, dict) and m.get("benchmark")}
    bseries = {b: closes(b, start, end) for b in sorted(bench)}

    per_market, entry_drift, outcomes = {}, [], {}
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
                    outcomes[id(r)] = ("no_entry_price", unpriced_reason(r, sup_by_key.get((r["market"], r["ticker"], r["side"])))) if entry is None \
                        else ("no_exit_price", f"entry close recorded but {why} up to {end.isoformat()}")
                    continue
                outcomes[id(r)] = ("priced", "")
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

    # ---- group A: every decision in the snapshot, priced or not (decision-behaviour statistics) ----
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None
    decisions = {}
    for key in list(per_market) + ["ALL"]:
        for side in ("BUY", "SELL"):
            mine = [r for r in rows if (key == "ALL" or r["market"] == key) and r["side"] == side]
            decisions[f"{key}|{side}"] = {
                "decisions": len(mine), "pricedForReturns": sum(outcomes[id(r)][0] == "priced" for r in mine),
                "noEntryPrice": sum(outcomes[id(r)][0] == "no_entry_price" for r in mine),
                "noExitPrice": sum(outcomes[id(r)][0] == "no_exit_price" for r in mine),
                "meanScore": mean([r.get("score") for r in mine]), "meanConfidence": mean([r.get("confidence") for r in mine]),
                "evidenceStatus": dict(collections.Counter(r.get("evidenceStatus") for r in mine)),
            }
    unpriced = [{"market": r["market"], "side": r["side"], "ticker": r["ticker"], "name": r.get("name"),
                 "category": outcomes[id(r)][0], "reason": outcomes[id(r)][1]}
                for r in rows if outcomes[id(r)][0] != "priced"]
    n_priced = sum(outcomes[id(r)][0] == "priced" for r in rows)
    assert n_priced + len(unpriced) == len(rows), "every decision must be priced or listed as unpriced"

    report = {"snapshot": snap["snapshotDate"], "end": end.isoformat(),
              "reconciliation": {"decisions": len(rows), "pricedForReturns": n_priced, "unpriced": len(unpriced)},
              "A_decisions_all": decisions,
              "B_returns_priced_subset": {"markets": per_market, "ALL_exchange_equal_weighted": summary},
              "C_unpriced": unpriced, "entryDriftOver2pct": entry_drift,
              "entriesFromSupplement": sum(1 for r in rows if r.get("fromSupplement")), "supplement": sup_path.name if fills else None}
    pct = lambda v: "   n/a " if v is None else f"{v*100:+7.2f}%"
    num = lambda v: "   n/a" if v is None else f"{v:+6.3f}"
    print(f"Paper portfolio {snap['snapshot'] if False else snap['snapshotDate']} -> {end}   decisions {len(rows)} = priced {n_priced} + unpriced {len(unpriced)}")
    print("\n(A) ALL DECISIONS - decision behaviour (priced or not; no returns)")
    print(f"{'market':<24}{'side':<6}{'n':>5}{'priced':>8}{'no entry':>10}{'no exit':>9}{'mean score':>12}{'mean conf':>11}  evidence")
    for k, v in decisions.items():
        m, side = k.split("|")
        print(f"{m:<24}{side:<6}{v['decisions']:>5}{v['pricedForReturns']:>8}{v['noEntryPrice']:>10}{v['noExitPrice']:>9}"
              f"{num(v['meanScore']):>12}{num(v['meanConfidence']):>11}  {v['evidenceStatus']}")
    print(f"\n(B) PRICED SUBSET ONLY - price returns, equal weight (ALL = exchanges equally weighted); n = priced/decisions")
    print(f"{'market':<26}{'BUY n':>7}{'BUY':>9}{'SELL n':>8}{'SELL':>9}{'bench':>9}{'BUY-bm':>9}{'SELL-bm':>9}{'BUY-SELL':>10}")
    for key, m in per_market.items():
        print(f"{key:<26}{m['BUY']['withData']:>3}/{m['BUY']['holdings']:<3}{pct(m['BUY']['equalWeightReturn'])}"
              f"{m['SELL']['withData']:>4}/{m['SELL']['holdings']:<3}{pct(m['SELL']['equalWeightReturn'])}{pct(m['benchmarkReturn'])}"
              f"{pct(m['BUY']['excessVsBenchmark'])}{pct(m['SELL']['excessVsBenchmark'])}{pct(m['BUY_minus_SELL'])}")
    print(f"{'ALL':<26}{'':>7}{pct(summary['BUY'])}{'':>8}{pct(summary['SELL'])}{pct(summary['benchmark'])}"
          f"{pct(summary['BUY_excess'])}{pct(summary['SELL_excess'])}{pct(summary['BUY_minus_SELL'])}")
    print(f"\n(C) NOT PRICED - excluded from (B) only, still counted in (A): {len(unpriced)}")
    for u in sorted(unpriced, key=lambda x: (x["market"], x["side"], x["ticker"])):
        print(f"  {u['market']:<22}{u['side']:<5}{u['ticker']:<10}{u['category']:<15}{u['reason']}")
    print(f"\nentries from supplement: {sum(1 for r in rows if r.get('fromSupplement'))}; entry close re-read differs >2% from stored: {len(entry_drift)}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


def unpriced_reason(row: dict, sup: dict | None) -> str:
    parts = [f"snapshot: {row.get('entryCloseError') or 'no entry close'}"]
    if sup is not None:
        why = sup.get("rejected") or sup.get("error") or "no usable close"
        prior = sup.get("priorClose")
        parts.append(f"supplement ({sup.get('vendorSymbol') or ', '.join(sup.get('symbolsTried', []))}): {why}"
                     + (f"; last prior close {prior['close']} on {prior['date']} not used" if prior else ""))
    return "; ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
