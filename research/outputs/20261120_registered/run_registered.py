#!/usr/bin/env python3
"""Run the OSF-registered returns script (commit 5f60385) UNCHANGED and keep the vendor data it read.

Usage:
  live    run_registered.py <script.py> <snapshot.json> <out_dir>             (reads Yahoo, writes vendor_pull.json.gz)
  replay  run_registered.py <script.py> <snapshot.json> <out_dir> --replay <vendor_pull.json.gz> [--end YYYY-MM-DD]   (offline)

The only thing replaced is the module's ``fetch`` function, by a wrapper that records (live) or plays back (replay) its return value.
All statistics, the seed (20261020) and the report come from the script's own ``main()``. per_holding.csv is computed with the script's
own ``total_return_leg`` on the same data, and is checked against the report's per-market means.
"""
import argparse, contextlib, csv, gzip, hashlib, importlib.util, io, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPT_SHA256 = "83140851d05f4dbfd71ac0bc33518f0336a90f24b8eeb811f5bbb9bccdde4668"
SNAPSHOT_SHA256 = "0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script"); ap.add_argument("snapshot"); ap.add_argument("out_dir")
    ap.add_argument("--replay"); ap.add_argument("--end", default="2026-11-20")
    a = ap.parse_args()
    assert sha(a.script) == SCRIPT_SHA256, "not the registered script"
    assert sha(a.snapshot) == SNAPSHOT_SHA256, "not the frozen snapshot"
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("registered_returns", a.script)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    live_fetch, seen = m.fetch, {}
    stored = json.loads(gzip.decompress(Path(a.replay).read_bytes()))["series"] if a.replay else None

    def fetch(symbol, start, end):
        if stored is not None:
            v = stored[symbol]; res = (v["close"], v["dividends"])
        else:
            res = live_fetch(symbol, start, end)
        seen[symbol] = {"close": res[0], "dividends": res[1]}
        return res

    m.fetch = fetch
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_path = out / f"returns_{a.end}.json"
    log = io.StringIO()
    sys.argv = [a.script, a.snapshot, "--end", a.end, "--json", str(report_path)]
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        rc = m.main()
    assert rc == 0
    (out / "run_log.txt").write_text(log.getvalue(), encoding="utf-8")
    report = json.loads(report_path.read_text())

    if stored is None:
        body = {"retrievedAtUtc": started, "source": "query1.finance.yahoo.com v8 chart, interval=1d, events=div",
                "series": {k: seen[k] for k in sorted(seen)}}
        (out / "vendor_pull.json.gz").write_bytes(gzip.compress(json.dumps(body, sort_keys=True).encode(), mtime=0))

    # per-holding rows, with the script's own functions on the same data
    snap = json.loads(Path(a.snapshot).read_text())
    stem = Path(a.snapshot)
    sup = json.loads(stem.with_name(stem.stem + "_entry_supplement.json").read_text())
    fills = {(f["market"], f["ticker"], f["side"]): f for f in sup["fills"]
             if f.get("close") is not None and f.get("closeDate") == snap["snapshotDate"]}
    dups = {(r["market"], r["ticker"], r["side"]): r for r in report["B_duplicates_excluded"]["rows"]}
    start, end = date.fromisoformat(snap["snapshotDate"]), date.fromisoformat(a.end)
    ref = min(end, datetime.now(timezone.utc).date())
    rows = []
    for r in snap["holdings"]:
        k = (r["market"], r["ticker"], r["side"])
        f = fills.get(k) if r.get("entryClose") is None else None
        sym = f["vendorSymbol"] if f else r.get("vendorSymbol")
        stored_entry = f["close"] if f else r.get("entryClose")
        v = seen.get(sym, {"close": {}, "dividends": {}})
        entry = v["close"].get(snap["snapshotDate"]) or stored_entry
        ret, xdate, why, dsum, flag = m.total_return_leg(v["close"], v["dividends"], snap["snapshotDate"], entry, end, ref)
        status, reason = "PRICED", ""
        if ret is None:
            status, reason = ("EXCLUDED", "no entry price" if entry is None else f"no exit price: {why}")
        if k in dups:
            d = dups[k]; status, reason = "EXCLUDED", f"duplicate ISIN {d['isin']}, counted on {d['keptMarket']} {d['keptTicker']}"
        rows.append({"market": r["market"], "ticker": r["ticker"], "side": r["side"], "vendorSymbol": sym or "", "status": status,
                     "reason": reason, "entryClose": "" if entry is None else repr(entry), "exitDate": xdate or "",
                     "dividends": repr(dsum) if ret is not None else "", "totalReturn": repr(ret) if ret is not None else "",
                     "exitFlag": flag or ""})
    with open(out / "per_holding.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    B = report["B_returns_priced_subset"]
    for mk, mv in B["markets"].items():
        for side in ("BUY", "SELL"):
            xs = [float(x["totalReturn"]) for x in rows if x["market"] == mk and x["side"] == side and x["status"] == "PRICED"]
            assert len(xs) == mv[side]["withData"], (mk, side, len(xs), mv[side]["withData"])
            assert not xs or abs(sum(xs) / len(xs) - mv[side]["equalWeightReturn"]) < 1e-9, (mk, side)
    p, s = B["ALL_exchange_equal_weighted"], B["spreadBootstrap"]["ALL"]
    summary = {"end": a.end, "seed": m.BOOTSTRAP_SEED, "resamples": m.BOOTSTRAP_N, "venues": len(B["markets"]),
               "buyPct": p["BUY"] * 100, "sellPct": p["SELL"] * 100, "benchmarkPct": p["benchmark"] * 100,
               "spreadPp": s["spread"] * 100, "spreadCi95Pp": [x * 100 for x in s["ci95"]], "nBuy": s["nBuy"], "nSell": s["nSell"],
               "reconciliation": report["reconciliation"], "venuesPositive": sum(mv["BUY_minus_SELL"] > 0 for mv in B["markets"].values()),
               "symbolsRequested": len(seen), "symbolsEmpty": sorted(k for k, v in seen.items() if not v["close"])}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
