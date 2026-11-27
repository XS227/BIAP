#!/usr/bin/env python3
"""Build the Decision Accuracy cohort file from the REGISTERED one-month output (read-only on every input).

Usage: python tools/decision_accuracy_import_registered.py <frozen_snapshot.json> <research/outputs/20261120_registered> <out.json>
  Refuses to overwrite <out.json>, and refuses inputs whose SHA-256 differs from SHA256SUMS.txt or the frozen snapshot hash.
  Numbers are copied as registered: no row is removed or corrected. Known data problems travel with the file as ``dataWarnings``.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

FROZEN_SHA256 = "0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1"
COHORT_ID = "v1-20261020-reg20261120"
USED = ("returns_2026-11-20.json", "per_holding.csv", "summary.json", "sensitivity_posthoc.json")


def canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    frozen, outputs, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    if out.exists():
        print(f"refusing to overwrite {out}")
        return 1
    raw = frozen.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_SHA256:
        print("frozen snapshot hash mismatch: not importing")
        return 1
    sums = dict(reversed(line.split()) for line in (outputs / "SHA256SUMS.txt").read_text().splitlines() if line.strip())
    for name in USED:
        if hashlib.sha256((outputs / name).read_bytes()).hexdigest() != sums.get(name):
            print(f"{name}: SHA-256 differs from SHA256SUMS.txt: not importing")
            return 1
    report = json.loads((outputs / "returns_2026-11-20.json").read_text())
    summary = json.loads((outputs / "summary.json").read_text())
    sens = json.loads((outputs / "sensitivity_posthoc.json").read_text())
    if report["snapshotSha256"] != FROZEN_SHA256 or report["end"] != "2026-11-20" or summary["seed"] != 20261020:
        print("output is not the registered run")
        return 1
    snap = json.loads(raw)
    with open(outputs / "per_holding.csv", encoding="utf-8", newline="") as f:
        priced = {(r["market"], r["side"], r["ticker"]): r for r in csv.DictReader(f)}
    decisions = []
    for h in snap["holdings"]:
        o = priced[(h["market"], h["side"], h["ticker"])]
        res = ({"status": "PRICED", "return": float(o["totalReturn"]), "exitDate": o["exitDate"], "exitFlag": o["exitFlag"] or None}
               if o["status"] == "PRICED" else {"status": "EXCLUDED", "reason": o["reason"]})
        decisions.append({"country": h["country"], "exchange": h["exchange"], "market": h["market"], "ticker": h["ticker"], "name": h.get("name"),
                          "side": h["side"], "tier": h["tier"], "score": h.get("score"), "confidence": h.get("confidence"), "rank": h.get("rank"),
                          "entryClose": h.get("entryClose"), "entryCloseDate": h.get("entryCloseDate"), "outcomes": {"1": res}})
    bench = {m: {"symbol": v["benchmark"], "returnPct": v["benchmarkReturn"] * 100.0, "exitDate": v["benchmarkExitDate"]}
             for m, v in report["B_returns_priced_subset"]["markets"].items()}
    clean = next(r for r in sens["runs"] if r["end"] == "2026-11-20" and r["rows"] == "without GVMH")
    warning = (f"Data warning: the price source gives a x100 unit error for one UK SELL holding (GVMH), counted as +9,900%. It drives the "
               f"pooled SELL return and spread shown here. Not registered, for information: without that one holding the venue-equal spread "
               f"is {clean['spreadPp']:+.2f} pp (95% interval {clean['ci95Pp'][0]:.2f} to {clean['ci95Pp'][1]:.2f}).")
    body = {"schema": 1, "cohortId": COHORT_ID, "decisionDate": snap["snapshotDate"], "decisionLogicVersion": "v1",
            "source": {"label": "registered evaluation, script commit 5f60385, exit 2026-11-20 (research/outputs/20261120_registered)",
                       "frozenSnapshot": "research/paper_portfolio_2026-10-20.json", "frozenSnapshotSha256": FROZEN_SHA256,
                       "registeredScriptCommit": "5f60385e5b46d251ee2180cfcdc160c3b721dbc6",
                       "outputSha256": {n: sums[n] for n in USED}},
            "returnBasis": "vendor TOTAL return (split-adjusted close plus cash dividends with ex-date after entry, no reinvestment), entry = close on the decision date",
            "horizonNotes": {"1": "exit 2026-11-20 = one calendar month after the decision date (registered endpoint)"},
            "registeredPooled": {"1": {"spreadCi95Pp": summary["spreadCi95Pp"], "bootstrapSeed": summary["seed"], "resamples": summary["resamples"]}},
            "dataWarnings": {"1": [warning]},
            "benchmarks": {"1": bench}, "decisions": decisions}
    body["contentSha256"] = canonical_sha(body)
    out.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(decisions)} decisions, {sum(d['outcomes']['1']['status'] == 'PRICED' for d in decisions)} priced")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
