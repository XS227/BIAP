#!/usr/bin/env python3
"""Reproducible 30-company benchmark per market, read-only, no network calls.

For every ledger market with stored daily history it selects 30 distinct common
equities: 10 by 30-session average traded value, 10 by 30-session return, 10 by
unusual-volume ratio (last completed session / mean of the 30 sessions before
it), de-duplicating across categories by taking the next eligible name. Then it
attaches the full stored BIAP pipeline output and the opportunity state.

Usage: opportunity_benchmark.py OUT_DIR [COUNTRY__EXCHANGE ...]
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "analysis"))
from global_markets.opportunity import classify_opportunity, rank_opportunities  # noqa: E402

LEDGERS = Path("/var/lib/biap-global/analysis-ledger")
HISTORY = Path("/var/lib/biap-global/history")
PER_CATEGORY = 10
WINDOW = 30
MAX_STALE_DAYS = 10
LIQUIDITY_FLOOR_PCTILE = 0.25   # return / unusual-volume ranks ignore the least liquid quartile (noise)
NON_COMMON = ("etf", "etn", "fund", "warrant", "right", "preferred", "certificate", "structured", "bond", "unit")


def load_history(path: Path, now: datetime):
    doc = json.loads(path.read_text())
    pts = [p for p in doc.get("points", []) if p.get("close") and p.get("date")]
    pts.sort(key=lambda p: p["date"])
    if len(pts) < WINDOW + 2:
        return None, "history shorter than 32 sessions"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    last = pts[-1]
    # A bar dated the same day the file was written may still be forming.
    if last["date"] == mtime.date().isoformat() and mtime.hour < 21:
        pts = pts[:-1]
        last = pts[-1]
    age = (now.date() - datetime.fromisoformat(last["date"]).date()).days
    if age > MAX_STALE_DAYS:
        return None, f"stale: last completed session {last['date']} ({age}d old)"
    window = pts[-WINDOW:]
    prior = pts[-WINDOW - 1:-1]
    base = pts[-WINDOW - 1]
    adj = lambda p: p.get("adjusted_close") or p["close"]
    vols = [p.get("volume") or 0 for p in window]
    prev_vols = [p.get("volume") or 0 for p in prior]
    avg_prev = sum(prev_vols) / len(prev_vols)
    if sum(1 for v in vols if v > 0) < 20:
        return None, "fewer than 20 traded sessions in last 30"
    return {
        "lastSession": last["date"], "lastClose": last["close"], "historyFileObservedAt": mtime.isoformat(),
        "provider": path.stem, "vendorSymbol": (doc.get("metadata") or {}).get("vendorSymbol"),
        "currency": (doc.get("identity") or {}).get("currency"),
        "avgTradedValue30d": statistics.fmean((p.get("volume") or 0) * p["close"] for p in window),
        "return30dPct": (adj(last) / adj(base) - 1.0) * 100.0,
        "volumeRatio": (last.get("volume") or 0) / avg_prev if avg_prev > 0 else None,
    }, None


def decode(blob):
    return json.loads(zlib.decompress(blob)) if blob else None


def pipeline_record(result: dict) -> dict:
    gov, dist, ev = result.get("governance") or {}, result.get("distress") or {}, result.get("evidence") or {}
    integ, table = result.get("decisionIntegrity") or {}, (result.get("decisionTable") or {})
    metrics = table.get("metrics") or {}
    opp = result.get("opportunity") or classify_opportunity(
        preliminary_call=integ.get("preliminaryCall") or result.get("call"), final_call=result.get("call"),
        score=result.get("score") or 0.0, confidence=result.get("confidence") or 0.0,
        evidence=ev, distress=dist, governance=gov, signals=result.get("signals"),
        metrics={"return6mPct": metrics.get("return6mPct")})
    credit = result.get("creditScoring") or {}
    return {
        "call": result.get("call"), "draftCall": integ.get("preliminaryCall"), "score": result.get("score"),
        "confidence": result.get("confidence"),
        "agents": {s["agent"]: {"vote": s["vote"], "confidence": s["confidence"], "reasoning": s["reasoning"]}
                   for s in result.get("signals") or []},
        "evidence": {"status": ev.get("status"), "missingCritical": ev.get("missing_critical"),
                     "coverage": ev.get("coverage"), "contradictions": ev.get("contradictions")},
        "agent8": {"action": gov.get("action"), "accepted": gov.get("accepted"), "hardBlocks": gov.get("hard_blocks"),
                   "reviewReasons": gov.get("review_reasons"), "reasoning": gov.get("reasoning")},
        "agent9": {"status": dist.get("status"), "models": dist.get("available_models"),
                   "missingInputs": dist.get("missing_inputs"), "reasoning": dist.get("reasoning")},
        "agent10": {"weightCoverage": credit.get("weight_coverage"), "missing": sorted((credit.get("factors_missing") or {}))},
        "metrics": {k: metrics.get(k) for k in (
            "pe", "pb", "evEbitda", "peVsSectorPct", "revenueYoyPct", "netMarginPct", "roePct", "debtToEquity",
            "currentRatio", "freeCashFlow", "return1mPct", "return3mPct", "return6mPct", "volatilityAnnualizedPct",
            "maxDrawdownPct", "volumeVs30d", "marketCap", "dividendYieldPct")},
        "outlook": {k: table.get(k) for k in ("shortTermOutlook", "longTermOutlook", "momentum", "riskLevel",
                                              "drawdownRisk", "valuationView")},
        "opportunity": opp,
    }


def benchmark_market(key: str, now: datetime) -> dict:
    country, exchange = key.split("__", 1)
    db = sqlite3.connect(f"file:{LEDGERS / (key + '.sqlite3')}?mode=ro", uri=True)
    rows = {r[0]: r for r in db.execute(
        "select ticker,name,status,call,score,confidence,result from ledger where in_universe=1")}
    hist_dir = HISTORY / country / exchange
    out = {"market": key, "generatedAt": now.isoformat(), "universeInLedger": len(rows), "excluded": {}, "companies": []}
    cands = []
    for path in sorted(hist_dir.glob("*/*.json")) if hist_dir.exists() else []:
        ticker = path.parent.name
        row = rows.get(ticker)
        if row is None:
            continue
        stats, why = load_history(path, now)
        if why:
            out["excluded"][why.split(":")[0]] = out["excluded"].get(why.split(":")[0], 0) + 1
            continue
        result = decode(row[6])
        itype = str(((result or {}).get("company") or {}).get("instrument_type") or "").lower()
        if any(tok in itype for tok in NON_COMMON):
            out["excluded"]["non-common-equity"] = out["excluded"].get("non-common-equity", 0) + 1
            continue
        cands.append({"ticker": ticker, "name": row[1], "status": row[2], "stats": stats, "result": result})
    out["eligible"] = len(cands)
    if not cands:
        out["limitation"] = "no verified daily history with >=32 sessions for any ledger instrument"
        return out
    floor = sorted(c["stats"]["avgTradedValue30d"] for c in cands)[int(len(cands) * LIQUIDITY_FLOOR_PCTILE)]
    chosen: dict[str, dict] = {}
    plan = (("TRADING_VALUE", "avgTradedValue30d", False), ("PRICE_APPRECIATION_30D", "return30dPct", True),
            ("UNUSUAL_VOLUME", "volumeRatio", True))
    for label, field, use_floor in plan:
        pool = [c for c in cands if c["stats"][field] is not None and (not use_floor or c["stats"]["avgTradedValue30d"] >= floor)]
        pool.sort(key=lambda c: c["stats"][field], reverse=True)
        taken = 0
        for c in pool:
            if c["ticker"] in chosen:
                continue
            chosen[c["ticker"]] = {**c, "category": label, "categoryRank": taken + 1}
            taken += 1
            if taken == PER_CATEGORY:
                break
        if taken < PER_CATEGORY:
            out.setdefault("shortfalls", {})[label] = PER_CATEGORY - taken
    for c in chosen.values():
        rec = {"ticker": c["ticker"], "name": c["name"], "category": c["category"], "categoryRank": c["categoryRank"],
               "market": {**c["stats"], "exchange": exchange, "country": country,
                          "source": c["stats"]["provider"]},
               "ledgerStatus": c["status"]}
        if c["result"]:
            rec["pipeline"] = pipeline_record(c["result"])
        else:
            rec["pipeline"] = None
            rec["limitation"] = f"ledger status {c['status']}: no stored pipeline result"
        out["companies"].append(rec)
    states: dict[str, int] = {}
    for rec in out["companies"]:
        s = rec["pipeline"]["opportunity"]["state"] if rec["pipeline"] else "INSUFFICIENT_DATA"
        states[s] = states.get(s, 0) + 1
    out["stateDistribution"] = states
    out["agent8Abstentions"] = {}
    for rec in out["companies"]:
        for reason in (rec["pipeline"] or {}).get("opportunity", {}).get("agent8Abstention", []):
            out["agent8Abstentions"][reason["code"]] = out["agent8Abstentions"].get(reason["code"], 0) + 1
    return out


def main() -> int:
    out_dir = Path(sys.argv[1]); out_dir.mkdir(parents=True, exist_ok=True)
    keys = sys.argv[2:] or sorted(p.stem for p in LEDGERS.glob("*.sqlite3"))
    now = datetime.now(timezone.utc)
    summary = []
    for key in keys:
        res = benchmark_market(key, now)
        (out_dir / f"{key}.json").write_text(json.dumps(res, indent=1, default=str))
        summary.append({k: res.get(k) for k in ("market", "universeInLedger", "eligible", "stateDistribution",
                                                 "agent8Abstentions", "shortfalls", "limitation", "excluded")}
                       | {"companies": len(res["companies"])})
        print(key, "eligible", res.get("eligible"), "selected", len(res["companies"]), res.get("stateDistribution"))
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
