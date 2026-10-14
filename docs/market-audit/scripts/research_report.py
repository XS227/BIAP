#!/usr/bin/env python3
"""Aggregate fresh_audit.py outputs into the research-readiness report (Markdown + JSON + manifest).

Usage: research_report.py AUDIT_DIR OUT_DIR   (AUDIT_DIR holds MARKET.audit.json and MARKET.scan.json)
Reads the production ledgers read-only for market-wide PASS/WARN/BLOCK counts. No network, no writes
outside OUT_DIR. Ranks opportunities by evidence (score x confidence among evidence-PASS names); it never
assigns or forces a BUY label - the label shown is the pipeline's own final call / opportunity state.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEDGERS = Path("/var/lib/biap-global/analysis-ledger")
GATES = ("G1_evidence_PASS", "G2_score_ge_0.25", "G3_confidence_ge_0.45", "G4_no_distress_block",
         "G5_no_contradiction", "G6_agent8_conf_ge_0.55")


def ledger_counts(key: str) -> dict:
    db = sqlite3.connect(f"file:{LEDGERS / (key + '.sqlite3')}?mode=ro", uri=True)
    ev = dict(db.execute("select coalesce(evidence_status,'NONE'),count(*) from ledger where in_universe=1 and status='COMPLETE' group by 1"))
    total = db.execute("select count(*) from ledger where in_universe=1").fetchone()[0]
    done = sum(ev.values())
    buys = db.execute("select count(*) from ledger where in_universe=1 and call='BUY_CANDIDATE' and evidence_status='PASS'").fetchone()[0]
    rng = db.execute("select min(analyzed_at),max(analyzed_at) from ledger where in_universe=1 and status='COMPLETE'").fetchone()
    return {"universe": total, "analysed": done, "PASS": ev.get("PASS", 0), "WARN": ev.get("WARN", 0),
            "BLOCK": ev.get("BLOCK", 0), "storedBuyCandidates": buys, "ledgerAnalysedRange": list(rng)}


def main() -> int:
    adir, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    markets = sorted(p.name[:-len(".audit.json")] for p in adir.glob("*.audit.json"))
    rows, allc, manifest_files = [], [], {}
    for m in markets:
        doc = json.loads((adir / f"{m}.audit.json").read_text())
        cs = doc["companies"]
        led = ledger_counts(m)
        ok = [c for c in cs if c["verdict"] != "RUN_ERROR"]
        ev = Counter(c["gates"]["G1_evidence_PASS"]["value"] for c in ok)
        scan = {}
        if (adir / f"{m}.scan.json").exists():
            txt = (adir / f"{m}.scan.json").read_text().replace("BIAP_SCAN_RESULT=", "").strip()
            try:
                scan = json.loads(txt)
            except ValueError:
                scan = {}
        gate_fail = Counter(g for c in ok for g in GATES if c["gates"][g]["result"] == "FAIL")
        rows.append({"market": m, **led, "benchmarkCompanies": len(cs), "runErrors": len(cs) - len(ok),
                     "benchmarkEvidence": dict(ev), "finalCalls": dict(Counter(c["finalCall"] for c in ok)),
                     "opportunityStates": dict(Counter(c["opportunityState"] for c in ok)),
                     "verdicts": dict(Counter(c["verdict"] for c in cs)), "gateFailures": dict(gate_fail),
                     "scan": {k: scan.get(k) for k in ("deepAnalyzed", "eligibleEquities", "recommendationCount", "status")}})
        for c in ok:
            allc.append({**c, "marketData": c.get("market"), "market": m})
        manifest_files[f"{m}.audit.json"] = hashlib.sha256((adir / f"{m}.audit.json").read_bytes()).hexdigest()
        (out / f"{m}.audit.json").write_text(json.dumps(doc, indent=1, default=str))

    ranked = sorted((c for c in allc if c["gates"]["G1_evidence_PASS"]["value"] == "PASS"
                     and c["opportunityState"] not in ("HIGH_RISK", "INSUFFICIENT_DATA")),
                    key=lambda c: -(c["score"] or 0) * (c["confidence"] or 0))[:25]
    near = sorted((c for c in allc if c["finalCall"] != "BUY_CANDIDATE"
                   and ((c["score"] or -9) >= 0.15 or c["draftCall"] == "BUY_CANDIDATE")),
                  key=lambda c: -(c["score"] or 0))
    result = {"generatedAt": datetime.now(timezone.utc).isoformat(), "markets": rows,
              "topByEvidence": [{k: c[k] for k in ("market", "ticker", "name", "category", "finalCall", "draftCall", "score",
                                                    "confidence", "opportunityState", "reason")} for c in ranked],
              "rejectedBuyCandidates": [{k: c[k] for k in ("market", "ticker", "name", "finalCall", "draftCall", "score", "confidence",
                                                           "verdict", "reason")}
                                        | {"failedGates": [g for g in GATES if c["gates"][g]["result"] == "FAIL"]} for c in near]}
    (out / "RESEARCH_READINESS.json").write_text(json.dumps(result, indent=1, default=str))

    md = ["# BIAP Global research-readiness report", "", f"Generated {result['generatedAt']}. Source: `fresh_audit.py` runs "
          "(isolated data dir, fresh pipeline incl. Agents 8/9/10), ledger counts read-only from production.", "",
          "## 1. Coverage and evidence gate (PASS/WARN/BLOCK)", "",
          "| Market | Universe | Analysed | PASS | WARN | BLOCK | Stored BUY | Top-30 PASS/WARN/BLOCK | Top-30 final calls | Verdicts |",
          "|---|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for r in rows:
        e = r["benchmarkEvidence"]
        md.append(f"| {r['market']} | {r['universe']} | {r['analysed']} | {r['PASS']} | {r['WARN']} | {r['BLOCK']} | {r['storedBuyCandidates']} | "
                  f"{e.get('PASS', 0)}/{e.get('WARN', 0)}/{e.get('BLOCK', 0)} | {r['finalCalls']} | {r['verdicts']} |")
    md += ["", "## 2. Top opportunities ranked by evidence (score x confidence, evidence PASS, excluding HIGH_RISK / INSUFFICIENT_DATA)", "",
           "Ranking is evidence-ordered; no BUY label is forced. `finalCall` is the pipeline's own governed call.", "",
           "| # | Market | Ticker | Name | Score | Conf | Final call | State |", "|---:|---|---|---|---:|---:|---|---|"]
    for i, c in enumerate(result["topByEvidence"], 1):
        md.append(f"| {i} | {c['market']} | {c['ticker']} | {c['name']} | {c['score']:+.3f} | {c['confidence']:.2f} | {c['finalCall']} | {c['opportunityState']} |")
    md += ["", "## 3. Rejected BUY candidates (score >= 0.15 or draft BUY_CANDIDATE, final call not BUY)", "",
           "| Market | Ticker | Score | Conf | Draft | Failed gates | Verdict | Reason |", "|---|---|---:|---:|---|---|---|---|"]
    for c in result["rejectedBuyCandidates"]:
        md.append(f"| {c['market']} | {c['ticker']} | {c['score']:+.3f} | {c['confidence']:.2f} | {c['draftCall']} | "
                  f"{', '.join(g.split('_')[0] for g in c['failedGates'])} | {c['verdict']} | {c['reason'][:110]} |")
    (out / "RESEARCH_READINESS.md").write_text("\n".join(md) + "\n")

    def sh(*a):
        try:
            return subprocess.run(a, capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
        except OSError:
            return None
    (out / "MANIFEST.json").write_text(json.dumps({
        "generatedAt": result["generatedAt"], "gitCommit": sh("git", "rev-parse", "HEAD"), "gitBranch": sh("git", "branch", "--show-current"),
        "python": platform.python_version(), "scripts": ["opportunity_benchmark.py", "fresh_audit.py", "research_report.py"],
        "method": "benchmark selection from stored history (2026-10-14 benchmark); fresh analyze_company per company in an isolated "
                  "BIAP_GLOBAL_DATA_DIR copy (fundamentals/history/universe/market/sector-reference copied, source cache read-through); "
                  "per-market isolated scan refresh (deep limit 50) provides the same-sector P/E cohort.",
        "sha256": manifest_files}, indent=1))
    print("markets", len(rows), "companies", len(allc), "ranked", len(ranked), "near", len(near))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
