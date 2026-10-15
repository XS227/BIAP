#!/usr/bin/env python3
"""Build the research-freeze dataset manifest, coverage and field-completeness statistics.

Usage: research_freeze.py OUT_DIR [LEDGER_BACKUP_DIR]
Read-only: opens production ledgers with mode=ro, hashes code/config/registry files, records the git commit.
Outputs OUT_DIR/FREEZE_MANIFEST.json and OUT_DIR/COVERAGE.json. No network access.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGERS = Path("/var/lib/biap-global/analysis-ledger")
CORE = ("revenue", "operating_income", "ebitda", "net_income", "total_assets", "total_liabilities", "total_equity",
        "current_assets", "current_liabilities", "total_debt", "operating_cash_flow", "free_cash_flow",
        "interest_expense", "retained_earnings", "pe", "pb", "ev_ebitda", "sector", "isin", "filing_period_end")
AGENTS = ("fundamental", "risk", "forecast", "comparison", "quality", "liquidity")
CODE_FILES = [
    "analysis/global_markets/service.py", "analysis/global_markets/governance.py",
    "analysis/global_markets/core_agents.py", "analysis/global_markets/advanced_agents.py",
    "analysis/global_markets/distress.py", "analysis/global_markets/credit_scoring.py",
    "analysis/global_markets/evidence_contract.py", "analysis/global_markets/opportunity.py",
    "analysis/global_markets/esef.py", "analysis/global_markets/german_reviewed_reports.py",
    "analysis/global_markets/data/de_verified_annual_reports.json",
    "analysis/global_markets/data/de_issuer_esef.json",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def ledger_stats(path: Path) -> dict:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    total = db.execute("select count(*) from ledger where in_universe=1").fetchone()[0]
    rows = db.execute("select result, evidence_status, call from ledger where in_universe=1 and status='COMPLETE' and result is not null")
    present, n, ev, calls = Counter(), 0, Counter(), Counter()
    agent_active = Counter()
    gov = Counter()
    periods: list[str] = []
    for blob, evs, call in rows:
        try:
            r = json.loads(zlib.decompress(blob))
        except Exception:  # noqa: BLE001
            continue
        n += 1
        ev[evs or "NONE"] += 1
        calls[call or "NONE"] += 1
        c = r.get("company") or {}
        for f in CORE:
            if c.get(f) not in (None, ""):
                present[f] += 1
        if c.get("filing_period_end"):
            periods.append(c["filing_period_end"])
        for s in r.get("signals") or []:
            if s.get("agent") in AGENTS and not (abs(s.get("vote", 0)) < 1e-9 and s.get("confidence", 1) <= 0.30):
                agent_active[s["agent"]] += 1
        g = (r.get("governance") or {}).get("action")
        if g:
            gov[g] += 1
    ts = db.execute("select min(analyzed_at), max(analyzed_at) from ledger where in_universe=1 and status='COMPLETE'").fetchone()
    return {
        "universe": total, "analysed": n, "evidence": dict(ev), "calls": dict(calls), "agent8": dict(gov),
        "fieldCompletenessPct": {f: round(100.0 * present[f] / n, 1) if n else None for f in CORE},
        "agentActivePct": {a: round(100.0 * agent_active[a] / n, 1) if n else None for a in AGENTS},
        "analysedRange": list(ts), "newestFilingPeriod": max(periods) if periods else None,
        "sha256": sha(path),
    }


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    backup = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    markets = {p.stem: ledger_stats(p) for p in sorted(LEDGERS.glob("*.sqlite3"))}
    cov = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "markets": markets,
        "totals": {
            "universe": sum(m["universe"] for m in markets.values()),
            "analysed": sum(m["analysed"] for m in markets.values()),
        },
    }
    (out / "COVERAGE.json").write_text(json.dumps(cov, indent=1))
    manifest = {
        "generatedAt": cov["generatedAt"],
        "gitCommit": git("rev-parse", "HEAD"),
        "gitBranch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "gitDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scoringConfiguration": {
            "architecture": "six scoring agents (fundamental, risk, forecast, comparison, quality, liquidity) + Agent 8 governance + Agent 9 distress + Agent 10 credit scoring",
            "aggregation": "confidence-weighted mean of agent votes in [-1,1]; final score and confidence multiplied by evidence confidence multiplier",
            "buyGate": {"score_gte": 0.25, "confidence_gte": 0.45, "evidenceStatus": "PASS", "agent9PositiveBlock": "must be false"},
            "avoidGate": {"score_lte": -0.25, "confidence_gte": 0.45},
            "noRecommendationBelowConfidence": 0.35,
            "agent8": {"accept_gte": 0.55, "escalate_gte": 0.35, "abstain_below": 0.35},
            "agent9Models": ["Zmijewski (1984)", "Altman Z'' (1995)", "interest coverage + synthetic rating band"],
            "thresholdsChangedThisProgram": False,
        },
        "codeAndConfigSha256": {f: sha(ROOT / f) for f in CODE_FILES if (ROOT / f).exists()},
        "ledgerBackupDir": str(backup) if backup else None,
        "ledgerSha256": {k: v["sha256"] for k, v in markets.items()},
        "sourceFamilies": sorted(p.name for p in Path("/var/lib/biap-global/cache").iterdir()),
        "universeFiles": {
            str(p.relative_to("/var/lib/biap-global/universe")): datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()
            for p in sorted(Path("/var/lib/biap-global/universe").glob("*/*.json"))
        },
    }
    (out / "FREEZE_MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    print("markets", len(markets), "universe", cov["totals"]["universe"], "analysed", cov["totals"]["analysed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
