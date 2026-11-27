#!/usr/bin/env python3
"""POST HOC, NOT REGISTERED: the registered spread and bootstrap (script's own functions, seed 20261020) without suspect vendor rows.

Usage: sensitivity_posthoc.py <registered script.py> <out_dir>   (offline; reads per_holding.csv files in out_dir)
"""
import collections, csv, importlib.util, json, sys
from pathlib import Path

SUSPECT = {("GB:LSE", "GVMH"): "price alternates 0.006 / 0.6 GBp (x100) on at most 254 shares of volume a day",
           ("GB:LSE", "PDL"): "price steps from 2.3 to 0.023 GBp (x100) on 2026-11-02, zero volume after",
           ("US:NASDAQ", "NUWE"): "vendor reports a 1:9 reverse split on 2026-10-27 but the entry close is not adjusted"}

spec = importlib.util.spec_from_file_location("registered_returns", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = Path(sys.argv[2])
result = {"label": "POST HOC sensitivity, not part of the registered analysis", "suspectRows": {f"{k[0]} {k[1]}": v for k, v in SUSPECT.items()}, "runs": []}
for end, name in (("2026-11-20", "per_holding.csv"), ("2026-11-19", "comparison_same_pull_per_holding_2026-11-19.csv")):
    rows = [r for r in csv.DictReader(open(out / name, encoding="utf-8")) if r["status"] == "PRICED"]
    markets = list(dict.fromkeys(r["market"] for r in rows))
    snapshot_order = list(m.BENCHMARKS)
    markets.sort(key=snapshot_order.index)
    for label, drop in (("as registered", set()), ("without GVMH", {("GB:LSE", "GVMH")}), ("without GVMH, PDL, NUWE", set(SUSPECT))):
        g = {mk: ([], []) for mk in markets}
        for r in rows:
            if (r["market"], r["ticker"]) not in drop:
                g[r["market"]][0 if r["side"] == "BUY" else 1].append(float(r["totalReturn"]))
        point, lo, hi = m.bootstrap_spread(g)["ALL"]
        result["runs"].append({"end": end, "rows": label, "nBuy": sum(len(v[0]) for v in g.values()), "nSell": sum(len(v[1]) for v in g.values()),
                               "buyPct": 100 * m.mean([m.mean(v[0]) for v in g.values()]), "sellPct": 100 * m.mean([m.mean(v[1]) for v in g.values()]),
                               "spreadPp": 100 * point, "ci95Pp": [100 * lo, 100 * hi],
                               "venuesPositive": sum(m.mean(v[0]) > m.mean(v[1]) for v in g.values())})
(out / "sensitivity_posthoc.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
for r in result["runs"]:
    print(f"{r['end']} {r['rows']:26} n {r['nBuy']}/{r['nSell']}  BUY {r['buyPct']:7.3f}  SELL {r['sellPct']:7.3f}  spread {r['spreadPp']:7.3f}  CI [{r['ci95Pp'][0]:.2f}, {r['ci95Pp'][1]:.2f}]  {r['venuesPositive']}/12")
