"""Background drain of every market's persistent analysis queue.

Interactive requests only advance a queue by a few companies so a phone never
waits on a long scan. This worker (systemd timer, every few minutes) keeps
draining the same SQLite ledgers until every eligible company has an audited
status. Each market runs in a fresh interpreter so RSS returns to the OS
between markets on the 2 GB host. Progress is committed per company, so a
restart or kill only loses the in-flight company.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from .analysis_ledger import AnalysisLedger, ledger_path
from .global_scan_refresh import _markets

MARKER = "BIAP_WORKER_RESULT="


def _needs_work(country: str, exchange: str) -> bool:
    if not ledger_path(country, exchange).exists():
        return True
    ledger = AnalysisLedger(country, exchange)
    try:
        ledger.requeue_transient()
        counts = ledger.counts(refresh_after_hours=float(os.environ.get("BIAP_GLOBAL_ANALYSIS_REFRESH_HOURS", "24")))
    finally:
        ledger.close()
    return counts["total"] == 0 or counts["queued"] > 0 or counts["refreshDue"] > 0


def _child(country: str, exchange: str, budget: float) -> int:
    from .scan_service import scan_global_market

    try:
        result = scan_global_market(
            country=country, exchange=exchange, top_n=10, discovery_limit=5000,
            deep_limit=500, origin="scheduled", time_budget_sec=budget,
        )
        ledger = result.get("analysisLedger") or {}
        summary = {
            "country": country, "exchange": exchange, "status": result.get("status"),
            "total": ledger.get("total"), "queued": ledger.get("queued"),
            "byStatus": ledger.get("byStatus"), "lastBatch": ledger.get("lastBatch"),
        }
    except Exception as exc:
        summary = {"country": country, "exchange": exchange, "status": "ERROR", "error": f"{type(exc).__name__}: {str(exc)[:260]}"}
    print(MARKER + json.dumps(summary, sort_keys=True, default=str))
    return 0


def _run_market(country: str, exchange: str, budget: float) -> dict:
    try:
        done = subprocess.run(
            [sys.executable, "-m", "global_markets.analysis_worker", "--market", country, exchange, str(budget)],
            check=False, capture_output=True, text=True, timeout=budget + 180, env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {"country": country, "exchange": exchange, "status": "ERROR", "error": "worker_subprocess_timeout"}
    for line in reversed(done.stdout.splitlines()):
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    return {"country": country, "exchange": exchange, "status": "ERROR", "error": (done.stderr or done.stdout or "no output").strip()[-260:]}


def main() -> int:
    per_market = float(os.environ.get("BIAP_GLOBAL_WORKER_MARKET_BUDGET_SEC", "240"))
    total = float(os.environ.get("BIAP_GLOBAL_WORKER_TOTAL_BUDGET_SEC", "1200"))
    started = time.monotonic()
    results = []
    # most-backlogged markets first would starve small ones; round-robin in fixed order
    for country, exchange in _markets():
        if time.monotonic() - started + per_market > total:
            results.append({"country": country, "exchange": exchange, "status": "DEFERRED_TO_NEXT_RUN"})
            continue
        if not _needs_work(country, exchange):
            results.append({"country": country, "exchange": exchange, "status": "SKIPPED_NOTHING_QUEUED_OR_DUE"})
            continue
        results.append(_run_market(country, exchange, per_market))
    print(json.dumps({"markets": len(results), "seconds": round(time.monotonic() - started, 1), "results": results}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--market":
        raise SystemExit(_child(sys.argv[2], sys.argv[3], float(sys.argv[4])))
    raise SystemExit(main())
