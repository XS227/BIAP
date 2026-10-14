#!/usr/bin/env python3
"""Fresh full-pipeline run + BUY-gate audit for the benchmark companies of one or more markets.

Reads the Top-30 selection from a benchmark directory (opportunity_benchmark.py output), re-runs the
complete existing pipeline (`global_markets.service.analyze_company`: Agents 1-7, Agent 8 governance,
Agent 9 distress, Agent 10 credit scoring) for every selected company against an ISOLATED data
directory (BIAP_GLOBAL_DATA_DIR, never the production one), checkpoints each result to disk, and writes
an audit record per company with the exact BUY gates passed/failed.

BUY gates (analysis/global_markets/service.py::_call and governance.py), thresholds NOT altered here:
  G1 evidence status == PASS          G2 score >= 0.25            G3 overall confidence >= 0.45
  G4 no Agent 9 positive_block        G5 no cross-agent contradictions
  G6 Agent 8 calibrated confidence >= 0.55 (accept); 0.35..0.55 -> REVIEW; < 0.35 -> ABSTAIN

Usage: fresh_audit.py BENCH_DIR OUT_DIR DATA_DIR MARKET [MARKET ...]
Resumable: an existing OUT_DIR/results/MARKET/TICKER.json is reused.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
import zlib
from pathlib import Path

LEDGERS = Path("/var/lib/biap-global/analysis-ledger")
IDENTITY = ("isin", "lei", "mic_code", "instrument_type", "sector", "industry", "reporting_currency", "lot_size")


def stored_identity(key: str, ticker: str) -> dict:
    """Identity fields (ISIN, MIC, LEI, ...) of the universe entry, read-only from the ledger row.

    The ISIN is required: sector classification is joined by exact ISIN, and the German/Euronext
    reference data are keyed by it. Only identity is taken; no analytical value is reused."""
    db = sqlite3.connect(f"file:{LEDGERS / (key + '.sqlite3')}?mode=ro", uri=True)
    row = db.execute("select result from ledger where ticker=?", (ticker,)).fetchone()
    if not row or not row[0]:
        return {}
    company = (json.loads(zlib.decompress(row[0])).get("company") or {})
    return {k: company.get(k) for k in IDENTITY if company.get(k) not in (None, "")}

CORE_FIELDS = ("revenue", "revenue_yoy_pct", "operating_income", "ebitda", "net_income", "total_assets",
               "total_liabilities", "total_equity", "current_assets", "current_liabilities", "total_debt",
               "operating_cash_flow", "free_cash_flow", "interest_expense", "pe", "pb", "ev_ebitda")
MIN_FREE_GB = 2.0


def gates(res: dict) -> dict:
    ev = (res.get("evidence") or {}).get("status")
    score, conf = res.get("score"), res.get("confidence")
    dist = res.get("distress") or {}
    gov = res.get("governance") or {}
    contra = (res.get("evidence") or {}).get("contradictions") or []
    ok = lambda b: "PASS" if b else "FAIL"
    return {
        "G1_evidence_PASS": {"result": ok(ev == "PASS"), "value": ev},
        "G2_score_ge_0.25": {"result": ok(score is not None and score >= 0.25), "value": score},
        "G3_confidence_ge_0.45": {"result": ok(conf is not None and conf >= 0.45), "value": conf},
        "G4_no_distress_block": {"result": ok(not dist.get("positive_block")), "value": dist.get("status")},
        "G5_no_contradiction": {"result": ok(not contra), "value": contra},
        "G6_agent8_conf_ge_0.55": {"result": ok(conf is not None and conf >= 0.55 and bool(gov.get("accepted"))),
                                   "value": gov.get("action")},
    }


def classify(res: dict, g: dict) -> tuple[str, str]:
    """(verdict, reason). Verdict: BUY | JUSTIFIED | DATA_LIMITED | REVIEW_DISAGREEMENT."""
    if res.get("call") == "BUY_CANDIDATE":
        return "BUY", "all gates passed"
    c = res.get("company") or {}
    ev = res.get("evidence") or {}
    missing_core = [f for f in CORE_FIELDS if c.get(f) is None]
    sig = {s["agent"]: s for s in res.get("signals") or []}
    neg = sorted(((s["vote"], a) for a, s in sig.items() if s["vote"] < -0.05))
    abstain = [a for a, s in sig.items() if abs(s["vote"]) < 1e-9 and s["confidence"] <= 0.30]
    if ev.get("status") != "PASS":
        return "DATA_LIMITED", f"evidence {ev.get('status')}: {ev.get('missing_critical') or ev.get('reasoning', '')[:80]}"
    if g["G5_no_contradiction"]["result"] == "FAIL":
        return "REVIEW_DISAGREEMENT", "agents disagree: " + "; ".join(map(str, ev.get("contradictions") or []))[:160]
    if g["G2_score_ge_0.25"]["result"] == "FAIL":
        if neg:
            return "JUSTIFIED", "score %.2f<0.25 with negative evidence-backed votes: %s" % (
                res.get("score") or 0, ", ".join(f"{a} {v:+.2f}" for v, a in neg[:3]))
        why = f"{len(missing_core)} of {len(CORE_FIELDS)} core fields missing" if missing_core else "neutral votes"
        kind = "DATA_LIMITED" if len(missing_core) >= 5 or len(abstain) >= 2 else "JUSTIFIED"
        return kind, f"score {res.get('score'):.2f}<0.25, no negative agent; {why}; abstaining agents: {abstain}"
    if g["G3_confidence_ge_0.45"]["result"] == "FAIL" or g["G6_agent8_conf_ge_0.55"]["result"] == "FAIL":
        return "DATA_LIMITED", f"score ok but confidence {res.get('confidence'):.2f}<0.55; missing {missing_core[:6]}"
    return "JUSTIFIED", "distress/governance restriction"


def audit_record(item: dict, res: dict) -> dict:
    c = res.get("company") or {}
    g = gates(res)
    verdict, reason = classify(res, g)
    srcs = [{"provider": s.get("provider"), "type": s.get("source_type"), "period": s.get("period_end"),
             "url": s.get("source_url")} for s in c.get("sources") or []]
    fund_src = [s for s in srcs if s["type"] and "market" not in s["type"] and "quote" not in s["type"]]
    sig = {s["agent"]: {"vote": s["vote"], "confidence": s["confidence"]} for s in res.get("signals") or []}
    dist, credit = res.get("distress") or {}, res.get("creditScoring") or {}
    table = (res.get("decisionTable") or {}).get("metrics") or {}
    return {
        "ticker": item["ticker"], "name": item["name"], "category": item["category"], "rank": item["categoryRank"],
        "isin": c.get("isin"), "sector": c.get("sector"), "market": item["market"],
        "finalCall": res.get("call"), "draftCall": (res.get("decisionIntegrity") or {}).get("preliminaryCall"),
        "score": res.get("score"), "confidence": res.get("confidence"),
        "agents": sig, "gates": g, "verdict": verdict, "reason": reason,
        "dataCompleteness": {"present": [f for f in CORE_FIELDS if c.get(f) is not None],
                             "missing": [f for f in CORE_FIELDS if c.get(f) is None],
                             "fundamentalSources": fund_src, "filingPeriodEnd": c.get("filing_period_end"),
                             "evidenceCoverage": (res.get("evidence") or {}).get("coverage"),
                             "freshnessTier": (res.get("fundamentalEvidence") or {}).get("freshnessTier")},
        "agent8": res.get("governance"), "agent9": {"status": dist.get("status"), "models": dist.get("available_models"),
                                                    "missingInputs": dist.get("missing_inputs")},
        "agent10": {"weightCoverage": credit.get("weight_coverage"), "missing": sorted(credit.get("factors_missing") or {})},
        "evidenceDetail": {k: table.get(k) for k in ("pe", "pb", "evEbitda", "peVsSectorPct", "revenueYoyPct",
                                                     "netMarginPct", "roePct", "debtToEquity", "currentRatio",
                                                     "return1mPct", "return3mPct", "return6mPct",
                                                     "volatilityAnnualizedPct", "maxDrawdownPct", "volumeVs30d")},
        "opportunityState": ((res.get("opportunity") or {}).get("state")),
    }


def main() -> int:
    bench, out, data = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    markets = sys.argv[4:]
    os.environ["BIAP_GLOBAL_DATA_DIR"] = str(data)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "analysis"))
    from global_markets.service import analyze_company          # noqa: E402
    from global_markets.models import GlobalCompany              # noqa: E402
    from global_markets.opportunity import classify_opportunity  # noqa: E402

    for key in markets:
        doc = json.loads((bench / f"{key}.json").read_text())
        rdir = out / "results" / key
        rdir.mkdir(parents=True, exist_ok=True)
        records = []
        for item in doc["companies"]:
            free_gb = shutil.disk_usage("/").free / 2**30
            if free_gb < MIN_FREE_GB:
                print(f"STOP: only {free_gb:.1f} GiB free", flush=True)
                return 3
            f = rdir / f"{item['ticker'].replace('/', '_')}.json"
            if f.exists():
                res = json.loads(f.read_text())
            else:
                cur = item["market"].get("currency") or "EUR"
                try:
                    ident = stored_identity(key, item["ticker"])
                    res = analyze_company(GlobalCompany(country=item["market"]["country"], exchange=item["market"]["exchange"],
                                                        ticker=item["ticker"], name=item["name"], currency=cur, **ident))
                except Exception as ex:  # keep going; record the failure explicitly
                    res = {"error": f"{type(ex).__name__}: {str(ex)[:300]}"}
                f.write_text(json.dumps(res, default=str))
                time.sleep(0.5)
            if "error" in res:
                records.append({"ticker": item["ticker"], "name": item["name"], "category": item["category"],
                                "verdict": "RUN_ERROR", "reason": res["error"]})
                print(key, item["ticker"], "ERROR", res["error"][:100], flush=True)
                continue
            if "opportunity" not in res:
                res["opportunity"] = classify_opportunity(
                    preliminary_call=(res.get("decisionIntegrity") or {}).get("preliminaryCall") or res.get("call"),
                    final_call=res.get("call"), score=res.get("score") or 0.0, confidence=res.get("confidence") or 0.0,
                    evidence=res.get("evidence") or {}, distress=res.get("distress") or {},
                    governance=res.get("governance") or {}, signals=res.get("signals"),
                    metrics={"return6mPct": ((res.get("decisionTable") or {}).get("metrics") or {}).get("return6mPct")})
            rec = audit_record(item, res)
            records.append(rec)
            print(key, item["ticker"], res.get("call"), rec["verdict"], flush=True)
        (out / f"{key}.audit.json").write_text(json.dumps({"market": key, "companies": records}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
