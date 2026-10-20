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
* ``--section A`` runs the decision statistics only: offline, no exit prices, no benchmark. "Priced" then means "has an entry price".
* Weights are renormalised over the priced holdings of each basket (equal weight among the holdings that have data).
* BUY-SELL spread: 95% bootstrap CI, 10,000 resamples of holdings (with replacement, within market and side), fixed seed 20261020.
  Markets with fewer than 10 priced holdings on either side are flagged "too small to interpret". ALL = mean of the per-market spreads.
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
import random
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


BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 20261020
MIN_PER_SIDE = 10


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def diff(a, b):
    return None if a is None or b is None else a - b


def bootstrap_spread(groups: dict[str, tuple[list[float], list[float]]]) -> dict:
    """groups: market -> (buy returns, sell returns). Spread = mean(buy) - mean(sell); ALL = mean over markets with both sides."""
    rng = random.Random(BOOTSTRAP_SEED)
    usable = {m: g for m, g in groups.items() if g[0] and g[1]}
    out = {}
    for m, (b, sl) in usable.items():
        draws = sorted(mean([rng.choice(b) for _ in b]) - mean([rng.choice(sl) for _ in sl]) for _ in range(BOOTSTRAP_N))
        out[m] = (mean(b) - mean(sl), draws[int(0.025 * BOOTSTRAP_N)], draws[int(0.975 * BOOTSTRAP_N) - 1])
    if usable:
        draws = sorted(mean([mean([rng.choice(b) for _ in b]) - mean([rng.choice(sl) for _ in sl]) for b, sl in usable.values()])
                       for _ in range(BOOTSTRAP_N))
        point = mean([mean(b) - mean(sl) for b, sl in usable.values()])
        out["ALL"] = (point, draws[int(0.025 * BOOTSTRAP_N)], draws[int(0.975 * BOOTSTRAP_N) - 1])
    return out


def unpriced_reason(row: dict, sup: dict | None) -> str:
    parts = [f"snapshot: {row.get('entryCloseError') or 'no entry close'}"]
    if sup is not None:
        why = sup.get("rejected") or sup.get("error") or "no usable close"
        prior = sup.get("priorClose")
        parts.append(f"supplement ({sup.get('vendorSymbol') or ', '.join(sup.get('symbolsTried', []))}): {why}"
                     + (f"; last prior close {prior['close']} on {prior['date']} not used" if prior else ""))
    return "; ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--end")
    ap.add_argument("--json")
    ap.add_argument("--supplement")
    ap.add_argument("--section", choices=["A", "all"], default="all")
    args = ap.parse_args()
    only_a = args.section == "A"
    raw = Path(args.snapshot).read_bytes()
    snap = json.loads(raw)
    sup_path = Path(args.supplement) if args.supplement else Path(args.snapshot).with_name(Path(args.snapshot).stem + "_entry_supplement.json")
    fills, sup_by_key = {}, {}
    if sup_path.exists():
        sup = json.loads(sup_path.read_text())
        if sup.get("snapshotSha256") != hashlib.sha256(raw).hexdigest():
            sys.exit(f"{sup_path.name} was built for a different snapshot file (sha256 mismatch)")
        sup_by_key = {(f["market"], f["ticker"], f["side"]): f for f in sup["fills"]}
        fills = {k: f for k, f in sup_by_key.items() if f.get("close") is not None and f.get("closeDate") == snap["snapshotDate"]}
    start = date.fromisoformat(snap["snapshotDate"])
    end = date.fromisoformat(args.end) if args.end else start + timedelta(days=31)
    if not only_a and end > datetime.now(timezone.utc).date():
        print(f"warning: end {end} is in the future; returns use the latest available close", file=sys.stderr)
    rows = snap["holdings"]
    for r in rows:                      # in-memory view only; the snapshot file is never written
        f = fills.get((r["market"], r["ticker"], r["side"])) if r.get("entryClose") is None else None
        if f:
            r["vendorSymbol"], r["entryClose"], r["fromSupplement"] = f["vendorSymbol"], f["close"], True
    markets = [k for k, m in snap["markets"].items() if isinstance(m, dict) and "benchmark" in m]

    per_market, entry_drift, outcomes, rets_by = {}, [], {}, collections.defaultdict(lambda: ([], []))
    if only_a:                          # priced = has an entry price; no network
        for r in rows:
            outcomes[id(r)] = ("priced", "") if r.get("entryClose") is not None else \
                ("no_entry_price", unpriced_reason(r, sup_by_key.get((r["market"], r["ticker"], r["side"]))))
    else:
        symbols = sorted({r["vendorSymbol"] for r in rows if r.get("vendorSymbol")})
        with ThreadPoolExecutor(max_workers=4) as pool:
            series = dict(zip(symbols, pool.map(lambda s: closes(s, start, end), symbols)))
        bseries = {b: closes(b, start, end) for b in sorted({snap["markets"][k]["benchmark"] for k in markets})}
        for key in markets:
            mk = snap["markets"][key]
            b = bseries.get(mk["benchmark"], {})
            bret, bdate, why = leg_return(b, snap["snapshotDate"], b.get(snap["snapshotDate"]), end)
            out = {"benchmark": mk["benchmark"], "benchmarkReturn": bret, "benchmarkExitDate": bdate, "benchmarkNote": why or None}
            for side in ("BUY", "SELL"):
                mine = [r for r in rows if r["market"] == key and r["side"] == side]
                pairs, rets = [], []
                for r in mine:
                    sr = series.get(r.get("vendorSymbol"), {})
                    entry = sr.get(snap["snapshotDate"]) or r.get("entryClose")
                    if r.get("entryClose") and sr.get(snap["snapshotDate"]) and abs(sr[snap["snapshotDate"]] / r["entryClose"] - 1) > 0.02:
                        entry_drift.append(r["ticker"])
                    ret, _, why = leg_return(sr, snap["snapshotDate"], entry, end)
                    if ret is None:
                        outcomes[id(r)] = ("no_entry_price", unpriced_reason(r, sup_by_key.get((r["market"], r["ticker"], r["side"])))) \
                            if entry is None else ("no_exit_price", f"entry close recorded but {why} up to {end.isoformat()}")
                        continue
                    outcomes[id(r)] = ("priced", "")
                    pairs.append((r["weight"], ret)); rets.append(ret)
                rets_by[key][0 if side == "BUY" else 1].extend(rets)
                r_ = weighted(pairs)
                out[side] = {"holdings": len(mine), "withData": len(pairs), "equalWeightReturn": r_,
                             "medianReturn": statistics.median(rets) if rets else None,
                             "excessVsBenchmark": diff(r_, bret),
                             "hitRateVsBenchmark": None if not rets or bret is None else sum(1 for x in rets if x > bret) / len(rets)}
            out["BUY_minus_SELL"] = diff(out["BUY"]["equalWeightReturn"], out["SELL"]["equalWeightReturn"])
            per_market[key] = out

    # ---- (A) all decisions; coverage; selection-bias check ----
    keys = markets + ["ALL"]
    decisions, coverage, bias = {}, {}, {}
    for key in keys:
        for side in ("BUY", "SELL"):
            mine = [r for r in rows if (key == "ALL" or r["market"] == key) and r["side"] == side]
            pr = [r for r in mine if outcomes[id(r)][0] == "priced"]
            un = [r for r in mine if outcomes[id(r)][0] != "priced"]
            decisions[f"{key}|{side}"] = {
                "decisions": len(mine), "priced": len(pr),
                "noEntryPrice": sum(outcomes[id(r)][0] == "no_entry_price" for r in mine),
                "noExitPrice": sum(outcomes[id(r)][0] == "no_exit_price" for r in mine),
                "meanScore": mean([r.get("score") for r in mine]), "meanConfidence": mean([r.get("confidence") for r in mine]),
                "evidenceStatus": dict(collections.Counter(r.get("evidenceStatus") for r in mine))}
            coverage[f"{key}|{side}"] = {"priced": len(pr), "total": len(mine), "pct": len(pr) / len(mine) if mine else None}
            ms_p, ms_u = mean([r["score"] for r in pr]), mean([r["score"] for r in un])
            mc_p, mc_u = mean([r["confidence"] for r in pr]), mean([r["confidence"] for r in un])
            bias[f"{key}|{side}"] = {"nPriced": len(pr), "nUnpriced": len(un), "meanScorePriced": ms_p, "meanScoreUnpriced": ms_u,
                                     "scoreDiff_priced_minus_unpriced": diff(ms_p, ms_u), "meanConfPriced": mc_p, "meanConfUnpriced": mc_u,
                                     "confDiff_priced_minus_unpriced": diff(mc_p, mc_u)}
    unpriced = [{"market": r["market"], "side": r["side"], "ticker": r["ticker"], "name": r.get("name"),
                 "category": outcomes[id(r)][0], "reason": outcomes[id(r)][1]} for r in rows if outcomes[id(r)][0] != "priced"]
    n_priced = sum(outcomes[id(r)][0] == "priced" for r in rows)
    assert n_priced + len(unpriced) == len(rows), "every decision must be priced or listed as unpriced"

    # ---- (B) spread with bootstrap CI ----
    spread = {}
    if not only_a:
        boot = bootstrap_spread({k: tuple(rets_by[k]) for k in markets})
        for k in markets + ["ALL"]:
            nb = sum(len(rets_by[m][0]) for m in markets) if k == "ALL" else len(rets_by[k][0])
            ns = sum(len(rets_by[m][1]) for m in markets) if k == "ALL" else len(rets_by[k][1])
            small = (min(len(rets_by[m][0]) for m in markets) < MIN_PER_SIDE or min(len(rets_by[m][1]) for m in markets) < MIN_PER_SIDE) \
                if k == "ALL" else (nb < MIN_PER_SIDE or ns < MIN_PER_SIDE)
            est = boot.get(k)
            spread[k] = {"spread": est[0] if est else None, "ci95": [est[1], est[2]] if est else None, "nBuy": nb, "nSell": ns,
                         "tooSmallToInterpret": bool(k != "ALL" and small),
                         "note": ("includes markets with <10 priced holdings per side" if k == "ALL" and small else None)}
        summary = {"BUY": mean([m["BUY"]["equalWeightReturn"] for m in per_market.values()]),
                   "SELL": mean([m["SELL"]["equalWeightReturn"] for m in per_market.values()]),
                   "benchmark": mean([m["benchmarkReturn"] for m in per_market.values()]),
                   "BUY_excess": mean([m["BUY"]["excessVsBenchmark"] for m in per_market.values()]),
                   "SELL_excess": mean([m["SELL"]["excessVsBenchmark"] for m in per_market.values()])}
    notes = ["Weights are renormalised over priced holdings: each basket is equal-weighted among the holdings that have data, "
             "not over all decisions.",
             "'Priced' = has an entry price" + ("" if only_a else " and a close after entry (entry and exit)") + ".",
             f"Bootstrap: {BOOTSTRAP_N} resamples, seed {BOOTSTRAP_SEED}, percentile 95% CI; markets with <{MIN_PER_SIDE} priced holdings "
             "on either side are marked 'too small to interpret'."]
    report = {"snapshot": snap["snapshotDate"], "snapshotSha256": hashlib.sha256(raw).hexdigest(), "section": args.section,
              "end": None if only_a else end.isoformat(), "notes": notes,
              "reconciliation": {"decisions": len(rows), "priced": n_priced, "unpriced": len(unpriced)},
              "A_decisions_all": decisions, "A_coverage": coverage, "A_selection_bias": bias, "C_unpriced": unpriced,
              "entriesFromSupplement": sum(1 for r in rows if r.get("fromSupplement")), "supplement": sup_path.name if fills else None}
    if not only_a:
        report["B_returns_priced_subset"] = {"markets": per_market, "ALL_exchange_equal_weighted": summary, "spreadBootstrap": spread}
        report["entryDriftOver2pct"] = entry_drift

    pct = lambda v: "   n/a " if v is None else f"{v*100:+7.2f}%"
    num = lambda v: "   n/a" if v is None else f"{v:+6.3f}"
    print(f"Paper portfolio {snap['snapshotDate']} (sha256 {report['snapshotSha256'][:12]}...)  section {args.section}"
          + ("" if only_a else f" -> {end}") + f"   decisions {len(rows)} = priced {n_priced} + unpriced {len(unpriced)}")
    for n in notes:
        print("  * " + n)
    print("\n(A1) ALL DECISIONS - decision behaviour (priced or not)")
    print(f"{'market':<22}{'side':<6}{'n':>5}{'priced':>8}{'no entry':>10}{'no exit':>9}{'mean score':>12}{'mean conf':>11}  evidence")
    for k, v in decisions.items():
        m, side = k.split("|")
        print(f"{m:<22}{side:<6}{v['decisions']:>5}{v['priced']:>8}{v['noEntryPrice']:>10}{v['noExitPrice']:>9}"
              f"{num(v['meanScore']):>12}{num(v['meanConfidence']):>11}  {v['evidenceStatus']}")
    print("\n(A2) COVERAGE - priced / total decisions")
    print(f"{'market':<22}{'BUY':>14}{'SELL':>14}")
    for key in keys:
        b, sl = coverage[f"{key}|BUY"], coverage[f"{key}|SELL"]
        print(f"{key:<22}{b['priced']:>5}/{b['total']:<4}{b['pct']*100:>4.0f}%{sl['priced']:>5}/{sl['total']:<4}{sl['pct']*100:>4.0f}%")
    print("\n(A3) SELECTION-BIAS CHECK - priced vs unpriced (difference = priced minus unpriced; n/a when a group is empty)")
    print(f"{'market':<22}{'side':<6}{'n pr/unpr':>10}{'score pr':>10}{'score un':>10}{'diff':>9}{'conf pr':>9}{'conf un':>9}{'diff':>9}")
    for k, v in bias.items():
        m, side = k.split("|")
        print(f"{m:<22}{side:<6}{v['nPriced']:>5}/{v['nUnpriced']:<4}{num(v['meanScorePriced']):>10}{num(v['meanScoreUnpriced']):>10}"
              f"{num(v['scoreDiff_priced_minus_unpriced']):>9}{num(v['meanConfPriced']):>9}{num(v['meanConfUnpriced']):>9}"
              f"{num(v['confDiff_priced_minus_unpriced']):>9}")
    if not only_a:
        print("\n(B) PRICED SUBSET - price returns, weights renormalised over priced holdings (ALL = markets equally weighted)")
        print(f"{'market':<24}{'BUY n':>8}{'BUY':>9}{'SELL n':>8}{'SELL':>9}{'bench':>9}{'BUY-bm':>9}{'SELL-bm':>9}")
        for key, m in per_market.items():
            print(f"{key:<24}{m['BUY']['withData']:>4}/{m['BUY']['holdings']:<3}{pct(m['BUY']['equalWeightReturn'])}"
                  f"{m['SELL']['withData']:>4}/{m['SELL']['holdings']:<3}{pct(m['SELL']['equalWeightReturn'])}{pct(m['benchmarkReturn'])}"
                  f"{pct(m['BUY']['excessVsBenchmark'])}{pct(m['SELL']['excessVsBenchmark'])}")
        print(f"{'ALL':<24}{'':>8}{pct(summary['BUY'])}{'':>8}{pct(summary['SELL'])}{pct(summary['benchmark'])}"
              f"{pct(summary['BUY_excess'])}{pct(summary['SELL_excess'])}")
        print("\n(B2) BUY minus SELL spread, bootstrap 95% CI")
        print(f"{'market':<24}{'nBUY':>6}{'nSELL':>7}{'spread':>10}{'95% CI':>22}  flag")
        for k, v in spread.items():
            ci = "n/a" if not v["ci95"] else f"[{v['ci95'][0]*100:+.2f}%, {v['ci95'][1]*100:+.2f}%]"
            flag = "too small to interpret" if v["tooSmallToInterpret"] else (v["note"] or "")
            print(f"{k:<24}{v['nBuy']:>6}{v['nSell']:>7}{pct(v['spread']):>10}{ci:>22}  {flag}")
    print(f"\n(C) NOT PRICED - {len(unpriced)} holdings; excluded from returns, still counted in (A)")
    for u in sorted(unpriced, key=lambda x: (x["market"], x["side"], x["ticker"])):
        print(f"  {u['market']:<22}{u['side']:<5}{u['ticker']:<10}{u['category']:<15}{u['reason']}")
    print(f"\nentries from supplement: {report['entriesFromSupplement']}"
          + ("" if only_a else f"; entry close re-read differs >2% from stored: {len(entry_drift)}"))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
