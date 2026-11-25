#!/usr/bin/env python3
"""Build the first Decision Accuracy track record from the FROZEN v1 paper cohort (read-only on every input).

Usage: python tools/decision_accuracy_import_v1.py <frozen_snapshot.json> <outputs_dir> <out.json> [--source-run <actions run id>] [--total-return]
  frozen_snapshot.json  research/paper_portfolio_2026-10-20.json (sha256 is verified; it is opened read-only and never written)
  outputs_dir           research/outputs/20261119_extra  (priced_holdings.csv, excluded_and_duplicates.csv, markets_and_pooled.csv, diagnostics.json)
  out.json              a NEW file; refuses to overwrite an existing one
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

FROZEN_SHA256 = "0bd9066e"          # prefix check below uses the full value
FROZEN_SHA256_FULL = "0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1"
COHORT_ID = "v1-20261020"


def canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def read_csv(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main(argv):
    args = list(argv[1:])
    run_id, total_return = None, False
    if "--total-return" in args:
        args.remove("--total-return")
        total_return = True
    if "--source-run" in args:
        i = args.index("--source-run")
        run_id = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__)
        return 2
    frozen_path, outputs, out = Path(args[0]), Path(args[1]), Path(args[2])
    if out.exists():
        print(f"refusing to overwrite {out}")
        return 1
    raw = frozen_path.read_bytes()                                   # read-only
    if hashlib.sha256(raw).hexdigest() != FROZEN_SHA256_FULL:
        print("frozen snapshot hash mismatch: not importing")
        return 1
    snap = json.loads(raw)
    diag = json.loads((outputs / "diagnostics.json").read_text(encoding="utf-8"))
    if diag.get("snapshot_sha256") != FROZEN_SHA256_FULL:
        print("diagnostics output is not bound to the frozen snapshot hash")
        return 1
    priced = {(r["market"], r["side"], r["ticker"]): r for r in read_csv(outputs / "priced_holdings.csv")}
    excluded = {(r["market"], r["side"], r["ticker"]): r["reason"] for r in read_csv(outputs / "excluded_and_duplicates.csv")}
    bench = {}
    for r in read_csv(outputs / "markets_and_pooled.csv"):
        if r.get("benchmark_symbol") and r["benchmark_symbol"] != "N/A" and r["benchmark_return_pct"] not in ("", None):
            bench[r["market"]] = {"symbol": r["benchmark_symbol"], "returnPct": float(r["benchmark_return_pct"]), "exitDate": r["benchmark_exit_date"]}
    decisions, seen = [], set()
    for h in snap["holdings"]:
        key = (h["market"], h["side"], h["ticker"])
        if key in seen:
            raise SystemExit(f"duplicate key in frozen holdings: {key}")
        seen.add(key)
        o = priced.get(key)
        if o is not None:
            out1 = {"status": "PRICED", "return": float(o["return"]), "exitDate": o["exitDate"], "exitFlag": o.get("exitFlag") or None}
        elif key in excluded:
            out1 = {"status": "EXCLUDED", "reason": excluded[key]}
        else:
            out1 = {"status": "EXCLUDED", "reason": "no entry price"}
        decisions.append({"country": h["country"], "exchange": h["exchange"], "market": h["market"], "ticker": h["ticker"], "name": h.get("name"),
                          "side": h["side"], "tier": h["tier"], "score": h.get("score"), "confidence": h.get("confidence"), "rank": h.get("rank"),
                          "entryClose": h.get("entryClose"), "entryCloseDate": h.get("entryCloseDate"), "outcomes": {"1": out1}})
    body = {"schema": 1, "cohortId": COHORT_ID, "decisionDate": snap["snapshotDate"], "decisionLogicVersion": "v1",
            "source": {"frozenSnapshot": "research/paper_portfolio_2026-10-20.json", "frozenSnapshotSha256": FROZEN_SHA256_FULL,
                       "diagnosticsOutputs": (f"GitHub Actions run {run_id} (artifact biap-nov19-frozen-cohort-{run_id}), diagnostics/" if run_id
                                   else "research/outputs/20261119_extra"), "diagnosticsEnd": diag.get("end")},
            "returnBasis": ("vendor TOTAL return (split-adjusted close plus cash dividends with ex-date after entry, no reinvestment), entry = close on the decision date"
                            if total_return else "vendor price return (split-adjusted close, no dividends), entry = close on the decision date"),
            "horizonNotes": {"1": "exit 2026-11-19 = 30 days after the decision date (one calendar month is 2026-11-20)"},
            "benchmarks": {"1": bench}, "decisions": decisions}
    body["contentSha256"] = canonical_sha({k: v for k, v in body.items()})
    out.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(decisions)} decisions, {sum(1 for d in decisions if d['outcomes']['1']['status']=='PRICED')} priced, {len(bench)} benchmarks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
