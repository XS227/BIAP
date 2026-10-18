#!/usr/bin/env python3
"""Read-only Swedish ranking-evidence audit against an existing BIAP ledger.

Never writes to the ledger, fetches bulk data, or changes ranking/BUY decisions.
Usage: python3 scripts/audit_sweden_ranking_evidence.py /path/to/SE__NASDAQ_STOCKHOLM.sqlite3
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import sqlite3
from pathlib import Path

CORE = ("revenue", "operating_income", "net_income", "total_assets",
        "total_equity", "operating_cash_flow")
SAMPLE = ("ACAST", "ACTI", "ALTRA", "ANNE.B", "ARION.SDB",
          "ARJO.B", "ATRLJ.B", "AVARDA", "BALD.B", "BETS.B")


def audit(path: Path, threshold: float = 60.0) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    # Immutable mode prohibits writes even to journal/WAL files.
    # For an active writer, take a consistent SQLite backup externally first.
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT ticker, name, status, evidence_status, source, financial "
            "FROM ledger WHERE in_universe=1 ORDER BY ticker"
        ).fetchall()
    finally:
        db.close()
    rejected = []
    missing_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for ticker, name, status, evidence, source, financial in rows:
        if evidence != "PASS":
            continue
        f = json.loads(financial or "{}")
        coverage = float(f.get("coveragePct") or 0)
        core_complete = f.get("coreComplete") in (True, 1)
        if core_complete and coverage >= threshold:
            continue
        missing = list(f.get("coreMissing") or [])
        reasons = f.get("missingReasons") or {}
        missing_counts.update(missing)
        source_counts[str(source or "unknown")] += 1
        reason_counts.update(f"{field}: {reasons.get(field, 'unclassified')}" for field in missing)
        rejected.append({
            "ticker": ticker, "name": name, "ledgerStatus": status,
            "source": source, "coveragePct": coverage,
            "coreComplete": core_complete, "coreMissing": missing,
            "missingReasons": {key: reasons.get(key) for key in missing},
            "belowCoverageThreshold": coverage < threshold,
        })
    by_ticker = {row["ticker"]: row for row in rejected}
    return {
        "universeRows": len(rows),
        "rankingRejectsWithEvidencePass": len(rejected),
        "coverageThresholdPct": threshold,
        "missingFieldCounts": dict(missing_counts.most_common()),
        "sourceCounts": dict(source_counts.most_common()),
        "missingReasonCounts": dict(reason_counts.most_common()),
        "sample": [by_ticker.get(t, {"ticker": t, "notInRejectedSet": True}) for t in SAMPLE],
        "allRejected": rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="Path to existing Swedish ledger SQLite file")
    parser.add_argument("--min-coverage", type=float, default=60.0)
    args = parser.parse_args()
    print(json.dumps(audit(args.ledger, args.min_coverage), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
