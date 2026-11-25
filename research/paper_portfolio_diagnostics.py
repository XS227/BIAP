#!/usr/bin/env python3
"""Post-freeze, read-only diagnostics for the BIAP 2026-10-20 paper portfolio.

Prices/dividends and entry handling match research/paper_portfolio_returns.py.
Current Yahoo Finance metadata is NOT a historical market-cap/sector snapshot.
Use --metadata-csv for point-in-time values when available. Outputs always report
source and coverage; no missing values are silently estimated.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from paper_portfolio_returns import BENCHMARKS, fetch, leg_return, total_return_leg

MIN_VOL_DAILY_RETURNS = 40
TRIM_FRACTION_EACH_TAIL = 0.05


def avg(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(values) if values else None


def med(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.median(values) if values else None


def spread(a, b):
    return None if a is None or b is None else a - b


def trimmed(values, proportion=TRIM_FRACTION_EACH_TAIL):
    """Symmetric 5% trim at EACH tail, independently in each basket."""
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    if not values:
        return None, 0
    n_drop = int(len(values) * proportion)
    middle = values[n_drop:len(values)-n_drop] if n_drop else values
    return avg(middle), n_drop


def prior_volatility(prices, entry_date, start_date):
    """Annualized standard deviation of daily log returns strictly BEFORE entry."""
    ordered = [(d, p) for d, p in sorted(prices.items())
               if start_date.isoformat() <= d < entry_date.isoformat() and p and p > 0]
    rets = [math.log(b / a) for (_, a), (_, b) in zip(ordered, ordered[1:])]
    if len(rets) < MIN_VOL_DAILY_RETURNS:
        return None, len(rets)
    return statistics.stdev(rets) * math.sqrt(252), len(rets)


def three_months_before(d):
    y, m = d.year, d.month - 3
    if m <= 0:
        m += 12
        y -= 1
    # Fixed snapshot is the twentieth; generalize to end-of-month inputs.
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def csv_write(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def percentage(value):
    return None if value is None else round(value * 100, 5)


def validate_bound_file(base, stem, snapshot_sha):
    path = base.with_name(base.stem + stem + ".json")
    if not path.exists():
        return {}, path
    value = json.loads(path.read_text())
    if value.get("snapshotSha256") != snapshot_sha:
        raise ValueError(f"{path.name}: sha256 mismatch with frozen snapshot")
    return value, path


def load_frozen(snapshot_path):
    raw = snapshot_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    snapshot = json.loads(raw)
    if snapshot.get("snapshotDate") != "2026-10-20":
        raise ValueError("Unexpected freeze date: refusing to blend cohorts")
    supplement, _ = validate_bound_file(snapshot_path, "_entry_supplement", sha)
    isinmap, _ = validate_bound_file(snapshot_path, "_isin_map", sha)
    fills = {(v["market"], v["ticker"], v["side"]): v
             for v in supplement.get("fills", [])
             if v.get("close") is not None and v.get("closeDate") == snapshot["snapshotDate"]}
    isins = {(v["market"], v["ticker"], v["side"]): v["isin"]
             for v in isinmap.get("entries", []) if v.get("isin")}
    rows = []
    for original in snapshot["holdings"]:
        row = dict(original)  # NEVER write into the frozen JSON
        k = (row["market"], row["ticker"], row["side"])
        row["isin"] = isins.get(k)
        if row.get("entryClose") is None and k in fills:
            row["entryClose"] = fills[k]["close"]
            row["vendorSymbol"] = fills[k]["vendorSymbol"]
            row["fromSupplement"] = True
        rows.append(row)
    return snapshot, sha, rows, bool(isinmap)


def choose_duplicates(rows, market_order):
    """Use exactly the same (ISIN, side) precedence as the preliminary run."""
    groups = collections.defaultdict(list)
    for row in sorted(rows, key=lambda r: market_order.index(r["market"])):
        if row.get("isin"):
            groups[(row["isin"], row["side"])].append(row)
    dup = set()
    for group in groups.values():
        if len({r["market"] for r in group}) <= 1:
            continue
        keep = next((r for r in group if r.get("entryClose") is not None), group[0])
        for r in group:
            if r["market"] != keep["market"]:
                dup.add(id(r))
    return dup


def read_metadata_csv(path):
    if not path:
        return {}
    data = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            symbol = (row.get("vendorSymbol") or row.get("vendor_symbol") or "").strip()
            market = (row.get("market") or "").strip()
            ticker = (row.get("ticker") or "").strip()
            if not symbol and not (market and ticker):
                raise ValueError("Metadata CSV needs vendorSymbol or both market and ticker")
            key = ("symbol", symbol) if symbol else ("market", market, ticker)
            cap = row.get("market_cap") or row.get("marketCap") or ""
            asof = row.get("as_of_date") or row.get("asOfDate") or ""
            data[key] = {
                "market_cap": float(cap) if cap else None,
                "sector": row.get("sector") or None,
                "as_of": asof,
                "source": "provided_metadata_csv",
            }
    return data


def yahoo_info(symbol):
    """Best-effort vendor quote metadata; never claim point-in-time accuracy."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).get_info() or {}
        cap = info.get("marketCap")
        return {"market_cap": float(cap) if isinstance(cap, (int, float)) and cap > 0 else None,
                "sector": info.get("sector") or info.get("sectorDisp") or None,
                "as_of": date.today().isoformat(),
                "source": "yahoo_current_not_point_in_time"}
    except Exception:
        return {"market_cap": None, "sector": None, "as_of": "", "source": "yahoo_unavailable"}


def describe(values):
    vals = [x["return"] for x in values]
    t, k = trimmed(vals)
    return {"n": len(vals), "mean_pct": percentage(avg(vals)),
            "median_pct": percentage(med(vals)),
            "trim5_each_tail_mean_pct": percentage(t),
            "trim_each_tail_n": k}


# ---------------------------------------------------------------------------
# Extra inference (added 2026-11-25). Pure functions, no network.
# ---------------------------------------------------------------------------
EXTRA_BOOTSTRAP_SEED = 20261119
EXTRA_BOOTSTRAP_B = 10000


def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, dd = 1.0, 1.0 - qab * x / qap
    dd = 1.0 / (dd if abs(dd) > tiny else tiny)
    h = dd
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        dd = 1.0 + aa * dd
        dd = 1.0 / (dd if abs(dd) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= dd * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        dd = 1.0 + aa * dd
        dd = 1.0 / (dd if abs(dd) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = dd * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t, df):
    """Two-sided p-value of Student's t with df degrees of freedom."""
    if df <= 0 or t is None or not math.isfinite(t):
        return None
    return _betainc(df / 2.0, 0.5, df / (df + t * t))


def exact_sign_test_p(n_pos, n_neg):
    """Exact two-sided binomial sign test (p=0.5); ties/zeros must already be dropped."""
    n = n_pos + n_neg
    if n == 0:
        return None
    k = min(n_pos, n_neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def venue_tests(market_spreads):
    """market_spreads: {venue: BUY mean - SELL mean (fraction)}. Venues with no spread are skipped."""
    vals = {k: v for k, v in market_spreads.items() if v is not None and math.isfinite(v)}
    n = len(vals)
    pos = sum(v > 0 for v in vals.values())
    neg = sum(v < 0 for v in vals.values())
    out = {"n_venues": n, "n_positive": pos, "n_negative": neg, "n_zero": n - pos - neg,
           "sign_test_p_two_sided": exact_sign_test_p(pos, neg),
           "mean_spread_pp": None, "t_stat": None, "df": n - 1 if n else None,
           "t_test_p_two_sided": None}
    if n >= 2:
        mean = statistics.fmean(vals.values())
        sd = statistics.stdev(vals.values())
        out["mean_spread_pp"] = percentage(mean)
        if sd > 0:
            out["t_stat"] = mean / (sd / math.sqrt(n))
            out["t_test_p_two_sided"] = t_two_sided_p(out["t_stat"], n - 1)
    return out


def market_spreads(rows):
    by = collections.defaultdict(lambda: {"BUY": [], "SELL": []})
    for r in rows:
        by[r["market"]][r["side"]].append(r["return"])
    return {m: (avg(v["BUY"]) - avg(v["SELL"]) if v["BUY"] and v["SELL"] else None)
            for m, v in by.items()}


def sector_neutral_spread(rows):
    """BUY-SELL spread within (market x sector) cells containing both sides.

    Cell spread = mean(BUY) - mean(SELL). Aggregates: weight nB*nS/(nB+nS) (primary) and
    equal weight per cell. UNKNOWN sector rows and one-sided cells are excluded and counted.
    """
    cells = collections.defaultdict(lambda: {"BUY": [], "SELL": []})
    unknown = 0
    for r in rows:
        if not r.get("sector") or r["sector"] == "UNKNOWN":
            unknown += 1
            continue
        cells[(r["market"], r["sector"])][r["side"]].append(r["return"])
    used, cell_rows = [], []
    for (market, sector), v in sorted(cells.items()):
        nb, ns = len(v["BUY"]), len(v["SELL"])
        row = {"market": market, "sector": sector, "n_buy": nb, "n_sell": ns,
               "buy_mean_pct": percentage(avg(v["BUY"])), "sell_mean_pct": percentage(avg(v["SELL"])),
               "spread_pct": None, "weight": None, "used": bool(nb and ns)}
        if nb and ns:
            sp = avg(v["BUY"]) - avg(v["SELL"])
            w = nb * ns / (nb + ns)
            row["spread_pct"], row["weight"] = percentage(sp), round(w, 4)
            used.append((sp, w, nb, ns))
        cell_rows.append(row)
    total_w = sum(w for _, w, _, _ in used)
    return {"cells": cell_rows, "n_cells": len(cells), "n_cells_used": len(used),
            "n_rows_unknown_sector": unknown,
            "n_buy_used": sum(nb for *_, nb, _ in used), "n_sell_used": sum(ns for *_, ns in used),
            "weighted_spread": (sum(sp * w for sp, w, _, _ in used) / total_w) if used else None,
            "equal_cell_spread": avg([sp for sp, _, _, _ in used])}


def _stat_triplet(sample):
    """sample: list of (market, side, sector, return). Returns the three bootstrap statistics."""
    pooled_b = [x[3] for x in sample if x[1] == "BUY"]
    pooled_s = [x[3] for x in sample if x[1] == "SELL"]
    pooled = avg(pooled_b) - avg(pooled_s) if pooled_b and pooled_s else None
    by = collections.defaultdict(lambda: ([], []))
    cells = collections.defaultdict(lambda: ([], []))
    for market, side, sector, ret in sample:
        i = 0 if side == "BUY" else 1
        by[market][i].append(ret)
        if sector != "UNKNOWN":
            cells[(market, sector)][i].append(ret)
    ms = [avg(b) - avg(s) for b, s in by.values() if b and s]
    num = den = 0.0
    for b, s in cells.values():
        if b and s:
            w = len(b) * len(s) / (len(b) + len(s))
            num += w * (avg(b) - avg(s))
            den += w
    return pooled, (avg(ms) if ms else None), (num / den if den else None)


def stratified_bootstrap(rows, B=EXTRA_BOOTSTRAP_B, seed=EXTRA_BOOTSTRAP_SEED, level=0.95):
    """Resample holdings with replacement WITHIN each (market, side) stratum (sizes preserved).

    Statistics: pooled holdings spread, equal-market-weight spread, sector-neutral weighted spread.
    Percentile CI. Deterministic for a given seed.
    """
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r["market"], r["side"])].append((r["market"], r["side"], r.get("sector") or "UNKNOWN", r["return"]))
    keys = sorted(strata)
    rng = random.Random(seed)
    draws = {"pooled": [], "equal_market": [], "sector_neutral": []}
    for _ in range(B):
        sample = []
        for k in keys:
            pool = strata[k]
            sample.extend(rng.choices(pool, k=len(pool)))
        p, e, sn = _stat_triplet(sample)
        for name, val in (("pooled", p), ("equal_market", e), ("sector_neutral", sn)):
            if val is not None:
                draws[name].append(val)
    point = dict(zip(("pooled", "equal_market", "sector_neutral"),
                     _stat_triplet([x for k in keys for x in strata[k]])))
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    out = {}
    for name, vals in draws.items():
        vals.sort()
        if len(vals) < 100:
            out[name] = {"point_pct": percentage(point[name]), "ci_low_pct": None, "ci_high_pct": None,
                         "n_valid_draws": len(vals), "B": B, "seed": seed}
            continue
        out[name] = {"point_pct": percentage(point[name]),
                     "ci_low_pct": percentage(vals[int(lo_q * (len(vals) - 1))]),
                     "ci_high_pct": percentage(vals[int(math.ceil(hi_q * (len(vals) - 1)))]),
                     "n_valid_draws": len(vals), "B": B, "seed": seed}
    return out


def extra_analyses(priced, output):
    """Write sector-neutral, venue-test and bootstrap outputs; return the report dict."""
    sector_proxy = not all(r.get("metadata_source") == "provided_metadata_csv"
                           and r.get("metadata_asof", "9999") <= "2026-10-20" for r in priced if r["sector"] != "UNKNOWN")
    basis = "POST_EVENT_PROXY" if sector_proxy else "POINT_IN_TIME"
    sn = sector_neutral_spread(priced)
    venues = market_spreads(priced)
    vt = venue_tests(venues)
    boot = stratified_bootstrap(priced)
    csv_write(output / "sector_neutral_cells.csv", sn["cells"],
              ["market", "sector", "n_buy", "n_sell", "buy_mean_pct", "sell_mean_pct", "spread_pct", "weight", "used"])
    venue_rows = [{"venue": m, "buy_minus_sell_pct": percentage(v)} for m, v in sorted(venues.items())]
    csv_write(output / "venue_spreads.csv", venue_rows, ["venue", "buy_minus_sell_pct"])
    csv_write(output / "bootstrap_ci.csv",
              [{"statistic": k, **v, "basis": basis if k == "sector_neutral" else "RETURNS_ONLY"} for k, v in boot.items()],
              ["statistic", "point_pct", "ci_low_pct", "ci_high_pct", "n_valid_draws", "B", "seed", "basis"])
    report = {"sector_basis": basis,
              "sector_neutral": {k: v for k, v in sn.items() if k != "cells"} | {
                  "weighted_spread_pct": percentage(sn["weighted_spread"]),
                  "equal_cell_spread_pct": percentage(sn["equal_cell_spread"])},
              "venue_tests": vt, "bootstrap_95": boot}
    for k in ("weighted_spread", "equal_cell_spread"):
        report["sector_neutral"].pop(k, None)
    (output / "extra_stats.json").write_text(json.dumps(report, indent=2, default=str))
    return report


def get_split(rows, attribute, market):
    usable = [r for r in rows if r["market"] == market
              and r.get(attribute) is not None and math.isfinite(r[attribute])]
    threshold = med([r[attribute] for r in usable])
    results = []
    if threshold is None:
        for group in ("low", "high"):
            results.append({"market": market, "group": group, "metric": attribute,
                            "median_cut": None, "n_buy": 0, "n_sell": 0,
                            "buy_mean_pct": None, "sell_mean_pct": None, "spread_pct": None,
                            "status": "NO_VALID_METADATA"})
        return results
    for group in ("low", "high"):
        subset = [r for r in usable if (r[attribute] <= threshold if group == "low"
                                       else r[attribute] > threshold)]
        b = [r["return"] for r in subset if r["side"] == "BUY"]
        s = [r["return"] for r in subset if r["side"] == "SELL"]
        bm, sm = avg(b), avg(s)
        point_in_time = all(r["cap_point_in_time"] for r in subset) if attribute == "market_cap" and subset else True
        status = ("OK" if b and s else "EMPTY_SIDE")
        if attribute == "market_cap" and not point_in_time:
            status += ";POST_EVENT_PROXY"
        if min(len(b), len(s)) < 5:
            status += ";SMALL_GROUP"
        results.append({
            "market": market, "group": group, "metric": attribute,
            "median_cut": round(threshold, 6), "n_buy": len(b), "n_sell": len(s),
            "buy_mean_pct": percentage(bm), "sell_mean_pct": percentage(sm),
            "spread_pct": percentage(spread(bm, sm)), "status": status})
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", default="research/paper_portfolio_2026-10-20.json")
    p.add_argument("--end", default="2026-11-18")
    p.add_argument("--out-dir", default="paper_portfolio_diagnostics")
    p.add_argument("--metadata-csv", default=None)
    p.add_argument("--metadata-mode", choices=["live", "none"], default="live")
    args = p.parse_args()
    path = Path(args.snapshot)
    snap, digest, rows, has_isins = load_frozen(path)
    entry_date, end = date.fromisoformat(snap["snapshotDate"]), date.fromisoformat(args.end)
    if end not in {date(2026, 11, 18), date(2026, 11, 19)}:
        raise SystemExit("Diagnostics permit only 2026-11-18 and 2026-11-19. Do not mix with the 20-Nov final.")
    history_start = three_months_before(entry_date)
    markets = [k for k, v in snap["markets"].items() if isinstance(v, dict) and "benchmark" in v]
    if not has_isins:
        raise SystemExit("Linked frozen ISIN map is required to deduplicate cross-listings.")
    duplicate_ids = choose_duplicates(rows, markets)

    # Historical prices, dividends, entry supplement, and ISIN exclusion mirror
    # paper_portfolio_returns.py; fetch a longer lookback for the volatility control.
    symbols = sorted({r["vendorSymbol"] for r in rows if r.get("vendorSymbol")})
    print(f"Fetching historical prices: {len(symbols)} symbols, {history_start} to {end}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        series = dict(zip(symbols, pool.map(lambda s: fetch(s, history_start, end), symbols)))
    ref = min(end, datetime.now(timezone.utc).date())
    excluded, priced = [], []
    unit_flags = []
    for row in rows:
        symbol = row.get("vendorSymbol")
        bars, divs = series.get(symbol, ({}, {}))
        vendor_entry = bars.get(entry_date.isoformat())
        entry = vendor_entry or row.get("entryClose")
        if entry is None or entry <= 0:
            excluded.append({"market": row["market"], "side": row["side"], "ticker": row["ticker"],
                             "vendorSymbol": symbol, "reason": "no_entry_price"})
            continue
        ret, exit_dt, why, dividends, exit_flag = total_return_leg(
            bars, divs, entry_date.isoformat(), entry, end, ref)
        if ret is None:
            excluded.append({"market": row["market"], "side": row["side"], "ticker": row["ticker"],
                             "vendorSymbol": symbol, "reason": "no_exit_price: " + why})
            continue
        if id(row) in duplicate_ids:
            excluded.append({"market": row["market"], "side": row["side"], "ticker": row["ticker"],
                             "vendorSymbol": symbol, "reason": "duplicate_isin_side"})
            continue
        vol, vol_n = prior_volatility(bars, entry_date, history_start)
        if dividends / entry > 0.50:
            unit_flags.append({"market": row["market"], "ticker": row["ticker"],
                               "dividends": dividends, "entry": entry, "ratio": dividends / entry})
        row.update({"return": ret, "exitDate": exit_dt, "exitFlag": exit_flag or "",
                    "dividends": dividends, "prior_volatility": vol,
                    "prior_vol_n": vol_n, "market_cap": None, "sector": "UNKNOWN",
                    "metadata_source": "missing", "metadata_asof": "", "cap_point_in_time": False})
        priced.append(row)

    external_meta = read_metadata_csv(args.metadata_csv)
    unique_symbols = sorted({r["vendorSymbol"] for r in priced if r.get("vendorSymbol")})
    online = {}
    if args.metadata_mode == "live":
        print(f"Fetching best-effort market cap / sector metadata: {len(unique_symbols)} symbols", flush=True)
        with ThreadPoolExecutor(max_workers=6) as pool:
            online = dict(zip(unique_symbols, pool.map(yahoo_info, unique_symbols)))
    for row in priced:
        key = ("market", row["market"], row["ticker"])
        info = external_meta.get(key) or external_meta.get(("symbol", row.get("vendorSymbol")))
        if info is None:
            info = online.get(row.get("vendorSymbol"), {})
        cap = info.get("market_cap")
        if cap is not None and (not math.isfinite(cap) or cap <= 0):
            cap = None
        row["market_cap"] = cap
        row["sector"] = (info.get("sector") or "UNKNOWN").strip() or "UNKNOWN"
        row["metadata_source"] = info.get("source", "missing")
        row["metadata_asof"] = info.get("as_of") or ""
        row["cap_point_in_time"] = bool(
            cap is not None and row["metadata_asof"]
            and row["metadata_asof"] <= entry_date.isoformat())

    by_market = collections.defaultdict(list)
    for r in priced:
        by_market[r["market"]].append(r)
    benchmark = {}
    for market in markets:
        symbol = BENCHMARKS.get(market, snap["markets"][market]["benchmark"])
        bars, _ = fetch(symbol, entry_date, end)
        bret, bdt, why = leg_return(bars, entry_date.isoformat(),
                                    bars.get(entry_date.isoformat()), end)
        benchmark[market] = {"symbol": symbol, "return": bret, "exit_date": bdt,
                             "issue": why or ""}

    summary = []
    for market in markets:
        b = describe([r for r in by_market[market] if r["side"] == "BUY"])
        s = describe([r for r in by_market[market] if r["side"] == "SELL"])
        summary.append({"market": market, "buy_n": b["n"], "sell_n": s["n"],
                        "buy_mean_pct": b["mean_pct"], "sell_mean_pct": s["mean_pct"],
                        "buy_median_pct": b["median_pct"], "sell_median_pct": s["median_pct"],
                        "median_spread_pp": percentage(spread(
                            med([r["return"] for r in by_market[market] if r["side"] == "BUY"]),
                            med([r["return"] for r in by_market[market] if r["side"] == "SELL"]))),
                        "buy_trimmed_pct": b["trim5_each_tail_mean_pct"],
                        "sell_trimmed_pct": s["trim5_each_tail_mean_pct"],
                        "trimmed_spread_pp": round(b["trim5_each_tail_mean_pct"] - s["trim5_each_tail_mean_pct"], 5)
                            if b["trim5_each_tail_mean_pct"] is not None and s["trim5_each_tail_mean_pct"] is not None else None,
                        "buy_trim_n_each_tail": b["trim_each_tail_n"],
                        "sell_trim_n_each_tail": s["trim_each_tail_n"],
                        "benchmark_symbol": benchmark[market]["symbol"],
                        "benchmark_return_pct": percentage(benchmark[market]["return"]),
                        "benchmark_exit_date": benchmark[market]["exit_date"]})
    bpool = describe([r for r in priced if r["side"] == "BUY"])
    spool = describe([r for r in priced if r["side"] == "SELL"])
    summary.append({"market": "ALL_HOLDINGS_POOL", "buy_n": bpool["n"], "sell_n": spool["n"],
                    "buy_mean_pct": bpool["mean_pct"], "sell_mean_pct": spool["mean_pct"],
                    "buy_median_pct": bpool["median_pct"], "sell_median_pct": spool["median_pct"],
                    "median_spread_pp": percentage(spread(
                        med([r["return"] for r in priced if r["side"] == "BUY"]),
                        med([r["return"] for r in priced if r["side"] == "SELL"]))),
                    "buy_trimmed_pct": bpool["trim5_each_tail_mean_pct"],
                    "sell_trimmed_pct": spool["trim5_each_tail_mean_pct"],
                    "trimmed_spread_pp": round(bpool["trim5_each_tail_mean_pct"] - spool["trim5_each_tail_mean_pct"], 5)
                        if bpool["trim5_each_tail_mean_pct"] is not None and spool["trim5_each_tail_mean_pct"] is not None else None,
                    "buy_trim_n_each_tail": bpool["trim_each_tail_n"],
                    "sell_trim_n_each_tail": spool["trim_each_tail_n"],
                    "benchmark_symbol": "N/A", "benchmark_return_pct": None,
                    "benchmark_exit_date": ""})
    for metric in ["buy_mean_pct", "sell_mean_pct", "buy_median_pct", "sell_median_pct",
                   "median_spread_pp", "buy_trimmed_pct", "sell_trimmed_pct", "trimmed_spread_pp"]:
        # Reference-consistent alternative: equal weight to each market.
        pass
    market_rows = summary[:len(markets)]
    summary.append({"market": "ALL_MARKETS_EQUAL_WEIGHT", "buy_n": bpool["n"], "sell_n": spool["n"],
                    **{k: round(avg([r[k] for r in market_rows]), 5) if avg([r[k] for r in market_rows]) is not None else None
                       for k in ("buy_mean_pct", "sell_mean_pct", "buy_median_pct", "sell_median_pct",
                                 "median_spread_pp", "buy_trimmed_pct", "sell_trimmed_pct", "trimmed_spread_pp")},
                    "buy_trim_n_each_tail": None, "sell_trim_n_each_tail": None,
                    "benchmark_symbol": "N/A", "benchmark_return_pct": None,
                    "benchmark_exit_date": ""})

    controls = []
    for market in markets:
        controls.extend(get_split(priced, "market_cap", market))
        controls.extend(get_split(priced, "prior_volatility", market))

    sector_rows = []
    for market in markets + ["ALL_HOLDINGS_POOL"]:
        group = priced if market == "ALL_HOLDINGS_POOL" else by_market[market]
        for side in ["BUY", "SELL"]:
            side_rows = [r for r in group if r["side"] == side]
            counts = collections.Counter(r["sector"] for r in side_rows)
            for sector, n in sorted(counts.items(), key=lambda p: (-p[1], p[0])):
                sector_rows.append({"market": market, "side": side, "sector": sector,
                                    "n": n, "pct_of_side": percentage(n / len(side_rows)) if side_rows else None})
    movers = []
    for market in ["ALL_HOLDINGS_POOL"] + markets:
        group = priced if market == "ALL_HOLDINGS_POOL" else by_market[market]
        for side in ["BUY", "SELL"]:
            side_rows = [r for r in group if r["side"] == side]
            for label, arr in (("biggest_losers", sorted(side_rows, key=lambda r: r["return"])[:10]),
                               ("biggest_winners", sorted(side_rows, key=lambda r: r["return"], reverse=True)[:10])):
                for rank, row in enumerate(arr, 1):
                    movers.append({"scope": market, "basket": side, "direction": label,
                                   "rank": rank, "ticker": row["ticker"], "vendor_symbol": row.get("vendorSymbol"),
                                   "market": row["market"], "return_pct": percentage(row["return"]),
                                   "exit_date": row["exitDate"], "exit_flag": row["exitFlag"]})
    coverage = []
    for market in markets + ["ALL_HOLDINGS_POOL"]:
        group = priced if market == "ALL_HOLDINGS_POOL" else by_market[market]
        for side in ["BUY", "SELL"]:
            side_rows = [r for r in group if r["side"] == side]
            coverage.append({"market": market, "side": side, "n_priced": len(side_rows),
                             "n_with_market_cap": sum(r["market_cap"] is not None for r in side_rows),
                             "n_cap_point_in_time": sum(r["cap_point_in_time"] for r in side_rows),
                             "n_with_sector": sum(r["sector"] != "UNKNOWN" for r in side_rows),
                             "n_with_prior_vol": sum(r["prior_volatility"] is not None for r in side_rows)})

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    extra = extra_analyses(priced, output)
    csv_write(output / "markets_and_pooled.csv", summary, list(summary[0]))
    csv_write(output / "size_and_prior_volatility_splits.csv", controls, list(controls[0]))
    csv_write(output / "top10_winners_losers.csv", movers, list(movers[0]))
    csv_write(output / "sector_mix.csv", sector_rows, ["market", "side", "sector", "n", "pct_of_side"])
    csv_write(output / "metadata_coverage.csv", coverage, list(coverage[0]))
    csv_write(output / "excluded_and_duplicates.csv", excluded,
              ["market", "side", "ticker", "vendorSymbol", "reason"])
    detail_fields = ["market", "side", "ticker", "vendorSymbol", "isin", "return", "exitDate", "exitFlag",
                     "dividends", "prior_volatility", "prior_vol_n", "market_cap", "sector",
                     "metadata_source", "metadata_asof", "cap_point_in_time"]
    csv_write(output / "priced_holdings.csv", priced, detail_fields)
    report = {"freeze": str(entry_date), "end": str(end), "snapshot_sha256": digest,
              "holdings": len(rows), "priced_issuers": len(priced), "excluded_rows": len(excluded),
              "exclusions_by_reason": dict(collections.Counter(e["reason"] for e in excluded)),
              "metadata_coverage": coverage, "benchmark": benchmark,
              "dividend_unit_sanity_over_50pct": unit_flags,
              "summary": summary, "controls": controls, "sector_mix": sector_rows}
    (output / "diagnostics.json").write_text(json.dumps(report, indent=2, default=str))

    notes = [
        "# BIAP paper-portfolio diagnostics (research-only)",
        f"Frozen source: {path}, SHA256 {digest}. No source mutation, server, deployment or release.",
        f"Snapshot 2026-10-20; latest allowed exit close {end.isoformat()}. Yahoo chart prices/dividends and ISIN-map rules match preliminary returns.",
        "Per-stock total return = (exit close + cash dividends after entry) / entry close - 1; latest close <= end.",
        "Median per side; symmetric trimmed mean drops floor(5% × n) from EACH tail within that market and side.",
        "ALL_HOLDINGS_POOL pools priced, ISIN-deduplicated holdings; ALL_MARKETS_EQUAL_WEIGHT averages 12 market-level estimates.",
        "Size split: median market cap of available priced BUY and SELL combined within each market. Yahoo live cap is POST-PERIOD and NOT point-in-time. Interpret those results as exploratory, not evidence of pre-entry size-adjusted effects.",
        "For point-in-time size results, provide --metadata-csv with market,ticker,market_cap,sector,as_of_date (YYYY-MM-DD <= 2026-10-20).",
        "Prior volatility: 3 calendar months ending before 2026-10-20; annualized sample std of daily log returns × sqrt(252); at least 40 observations.",
        "Sector mix: share of priced holdings per side; UNKNOWN is explicit, not silently dropped. Yahoo profile sector may be current, not as-of entry.",
        "Post-freeze vendor metadata may be missing / rate-limited. Every market and side has coverage counts; do not treat missing group estimates as zero.",
        "Each control group reports both BUY and SELL sample sizes; sparse/one-sided groups must not support causal interpretation.",
        "Extra (added 2026-11-25): sector_neutral_cells.csv / extra_stats.json = BUY-SELL spread within market x sector cells holding both sides (weight nB*nS/(nB+nS); equal-cell also reported); venue_spreads.csv + venue_tests = sign test (exact binomial) and one-sample t-test across venue-level BUY-SELL spreads; bootstrap_ci.csv = 95% percentile CI, 10,000 draws, resampling within (market, side) strata, seed 20261119. Sector and market cap come from current Yahoo metadata and are labelled POST_EVENT_PROXY, not point-in-time.",
        "Not an experimental randomized design and not proof of predictive skill. Flag stale exits, extreme dividends, and benchmark gaps.",
    ]
    (output / "README.md").write_text("\n\n".join(notes) + "\n", encoding="utf-8")
    print("\nMARKET                   BUY median  SELL median  BUY trim5  SELL trim5  TRIM spread  n BUY/SELL")
    for r in summary:
        def fmt(v):
            return "   n/a " if v is None else f"{v:+7.2f}%"
        print(f"{r['market']:<27}{fmt(r['buy_median_pct']):>11}{fmt(r['sell_median_pct']):>13}"
              f"{fmt(r['buy_trimmed_pct']):>11}{fmt(r['sell_trimmed_pct']):>12}"
              f"{fmt(r['trimmed_spread_pp']):>13}  {r['buy_n']}/{r['sell_n']}")
    print("\nCONTROL BY MARKET AND GROUP (cap=current metadata unless CSV supplies as-of snapshot):")
    for r in controls:
        print(f"{r['market']:<22}{r['metric']:<20}{r['group']:<5} BUY {r['n_buy']:<3} SELL {r['n_sell']:<3}"
              f" spread={r['spread_pct']}pp {r['status']}")
    print("\nEXTRA (sector basis %s):" % extra["sector_basis"])
    print(json.dumps({k: v for k, v in extra.items() if k != "sector_basis"}, indent=2, default=str))
    print("\nTOP 10 WINNERS/LOSERS PER BASKET (pooled):")
    for r in movers:
        if r["scope"] == "ALL_HOLDINGS_POOL":
            print(f"{r['basket']:<4} {r['direction']:<16} #{r['rank']:>2} {r['ticker']:<16} {r['market']:<22} {r['return_pct']:+.2f}%")
    print("\nSECTOR MIX (pooled):")
    for r in sector_rows:
        if r["market"] == "ALL_HOLDINGS_POOL":
            print(f"{r['side']:<4} {r['sector']:<30} {r['n']:>4} {r['pct_of_side']}%")
    print("\nEXCLUSIONS:", dict(collections.Counter(e["reason"] for e in excluded)))
    print("SANITY: dividends >50% of entry:",len(unit_flags))
    print("Metadata coverage (pooled):", [r for r in coverage if r["market"] == "ALL_HOLDINGS_POOL"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
