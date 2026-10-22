#!/usr/bin/env python3
"""Advance the persistent listed-company baseline by one bounded daily batch.

This is intentionally separate from the daily Tindex Market Memory collector:
- Market Memory keeps a small, recent Tindex observation available every day.
- This worker refreshes the heavier TSETMC/CODAL/Tindex company baseline on a
  rolling cycle. Production advances 300 companies/day, then wraps to the
  beginning after the full TSE/IFB/IFB_BASE universe has been visited.

Missing upstream data is recorded; it is never imputed or fabricated.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

import baseline_report
import codal_data
import tindex_indices
from company_registry_store import CompanyRegistryStore
from instrument_classifier import normalize_text
from listed_company_ingestion import WORKER_NAME, run_batch
from listed_company_store import ListedCompanyStore


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 30.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _new_filing_codes(store: ListedCompanyStore) -> list[str]:
    """Codes of companies that filed financial statements since the last completed check.

    One symbol-less CODAL search per page (<= 5) instead of a per-company probe. The check date is
    only advanced after a successful search, so a 429 here means the same window is retried next run.
    """
    state = store.get_state(WORKER_NAME) or {}
    last = (state.get("metadata") or {}).get("lastFilingCheckDate")
    since = date.fromisoformat(last) if last else date.today() - timedelta(days=7)
    symbols = {normalize_text(x) for x in codal_data.symbols_with_new_financial_filings(since)}
    if not symbols:
        return []
    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute("SELECT code, symbol FROM instrument_registry WHERE is_duplicate_instrument=0").fetchall()
    return [code for code, symbol in rows if normalize_text(symbol) in symbols]


def _run_tindex() -> dict | None:
    """TIndex is best-effort: a failure there (bad token, outage) must not lose the saved CODAL
    result or the report, so it is reported as an early stop instead of crashing the run."""
    if not tindex_indices._token():
        return None
    try:
        return tindex_indices.run()
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        code = getattr(exc, "code", None)
        reason = f"HTTP {code}" if code else type(exc).__name__
        return {"source": "TIndex", "succeeded": 0, "failed": 0, "rateLimited": 0, "stoppedEarly": f"TIndex unavailable: {reason}"}


def main() -> int:
    batch_size = _env_int("BIAP_LISTED_COMPANY_DAILY_BASELINE_BATCH", 300)
    backlog_per_run = _env_int("BIAP_LISTED_COMPANY_BACKLOG_PER_RUN", 25, minimum=0, maximum=100)
    interval = _env_float("BIAP_LISTED_COMPANY_INTERVAL_SECONDS", 2.5)
    store = ListedCompanyStore()
    filing_check_error = None
    try:
        filing_codes = _new_filing_codes(store)
        check_date = datetime.now(timezone.utc).date().isoformat()
    except codal_data.CodalDataUnavailable as exc:
        filing_check_error = f"new-filings check failed ({str(exc)[:100]}); same window retried next run"
        filing_codes = []
        check_date = None  # keep the previous check date; the same window is retried next run
        codal_data.clear_rate_limit()
    result = run_batch(
        store=store, batch_size=batch_size, interval_seconds=interval,
        backlog_per_run=backlog_per_run, new_filing_codes=filing_codes,
    )
    meta = result.get("metadata") or {}
    if check_date:
        meta["lastFilingCheckDate"] = check_date
    if filing_check_error:
        meta["newFilingCheckError"] = filing_check_error
    store.save_state(
        WORKER_NAME, status=result["status"], cursor=result["cursor"], total=result["total"], processed=result["processed"],
        succeeded=result["succeeded"], failed=result["failed"], started_at=result.get("startedAt"),
        completed_at=result.get("completedAt"), last_code=result.get("lastCode"), last_error=result.get("lastError"), metadata=meta,
    )
    tindex_result = _run_tindex()
    report = baseline_report.build_report(
        {**result, "metadata": meta}, tindex_result, meta.get("priceSources") or {}, max(0, int(result["total"]) - int(result["cursor"])),
    )
    report["notification"] = baseline_report.send(report)
    result = {**result, "tindex": tindex_result, "report": report}
    result = {
        **result,
        "requestedBatchSize": batch_size,
        "intervalSeconds": interval,
        "policy": "rolling persistent baseline; throttled upstream access; no fabricated values",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    # Individual upstream misses -- and a CODAL/TIndex rate-limit stop (status "rate_limited", progress
    # already saved) -- are persisted in the worker state and exit 0: systemd must not mark the unit
    # failed or retry into the same 429. Only an empty/uninitialized store is an operational failure.
    return 0 if int(result.get("total") or 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
