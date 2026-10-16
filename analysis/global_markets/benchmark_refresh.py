"""Lightweight, online-first refresh of one market's peer-benchmark scan cache.

Designed for a 24 h timer (Germany/XETRA first). Guarantees:
  * online-first, bounded by ``time_budget_sec``; no downloads are persisted
    except the single scan-cache JSON of that market (~0.5 MB, atomically replaced);
  * the new payload is validated before it can replace the existing cache; on
    any failure the previous cache is left byte-for-byte untouched and the
    decision layer keeps failing closed once that cache passes 24 h (see
    ``_critical_data_gaps`` / governance), so a failed refresh can never
    produce a BUY;
  * the previous file is kept as ``<market>.json.prev`` (one generation, same
    directory) so a bad refresh can be rolled back with a single ``mv``.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

from .scan_service import _SCAN_CACHE_SCHEMA_VERSION, _scan_cache_path
from .source_cache import read_json, write_json_atomic

MIN_DEEP_ROWS = 50
MIN_SCREENING_COVERAGE_PCT = 90.0
MAX_ROW_SHRINK = 0.5  # new deep rows must be >= 50% of the previous cache
STALE_TMP_AGE_SEC = 3600  # orphaned *.tmp from a killed run are removed after 1 h

log = logging.getLogger("biap.benchmark_refresh")


class RefreshLocked(RuntimeError):
    """Another refresh for the same market is running."""


@contextmanager
def refresh_lock(path: Path) -> Iterator[None]:
    """Non-blocking exclusive lock (released by the kernel if the process dies)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_name(path.name + ".lock"), "w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefreshLocked(str(path)) from exc
        yield
    finally:
        handle.close()


def cleanup_stale_temp(path: Path, max_age_sec: float = STALE_TMP_AGE_SEC) -> int:
    """Remove only this cache file's own orphaned temp files (never .json/.prev)."""
    removed = 0
    for tmp in path.parent.glob(path.name + ".*.tmp"):
        try:
            if time.time() - tmp.stat().st_mtime > max_age_sec:
                tmp.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def validate_payload(payload: object, previous_rows: int = 0) -> list[str]:
    """Reasons the payload must NOT replace the cache (empty list = acceptable)."""
    if not isinstance(payload, dict):
        return ["payload is not an object"]
    problems: list[str] = []
    rows = payload.get("deepResults")
    if not isinstance(rows, list):
        return ["deepResults missing"]
    valid = [r for r in rows if isinstance(r, dict) and isinstance(r.get("company"), dict)]
    if len(valid) < MIN_DEEP_ROWS:
        problems.append(f"only {len(valid)} valid deep rows (< {MIN_DEEP_ROWS})")
    if previous_rows and len(valid) < previous_rows * MAX_ROW_SHRINK:
        problems.append(f"deep rows shrank {previous_rows} -> {len(valid)}")
    if payload.get("rankingEligible") is not True:
        problems.append("rankingEligible is not true")
    coverage = payload.get("screeningCoveragePct")
    if not isinstance(coverage, (int, float)) or coverage < MIN_SCREENING_COVERAGE_PCT:
        problems.append(f"screening coverage {coverage!r} < {MIN_SCREENING_COVERAGE_PCT}")
    return problems


def refresh_benchmark(
    country: str,
    exchange: str,
    *,
    time_budget_sec: float = 480.0,
    scan: Optional[Callable[..., dict]] = None,
    now: Optional[datetime] = None,
) -> dict:
    country, exchange = country.upper(), exchange.upper()
    path = _scan_cache_path(country, exchange)
    previous = read_json(path, default=None)
    prev_payload = previous.get("payload") if isinstance(previous, dict) else None
    prev_rows = len(prev_payload.get("deepResults") or []) if isinstance(prev_payload, dict) else 0
    result = {"country": country, "exchange": exchange, "status": "ERROR", "replaced": False, "previousRows": prev_rows}
    try:
        if scan is None:
            from .scanner import GlobalMarketScanner

            def scan(**kw):  # noqa: E306 - bounded direct scan, nothing is written by the scanner itself
                return GlobalMarketScanner().scan(
                    country=kw["country"], exchange=kw["exchange"], top_n=10,
                    discovery_limit=5000, deep_limit=25, time_budget_sec=kw["time_budget_sec"],
                )

        payload = scan(country=country, exchange=exchange, time_budget_sec=time_budget_sec)
    except Exception as exc:  # network/provider failure: keep the old cache
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return result
    problems = validate_payload(payload, prev_rows)
    if problems:
        result.update(status="REJECTED", problems=problems)
        return result
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    wrapper = {
        "schemaVersion": _SCAN_CACHE_SCHEMA_VERSION,
        "scanOrigin": "benchmark-refresh",
        "cachedAt": stamp,
        "country": country,
        "exchange": exchange,
        "payload": {**payload, "scanOrigin": "benchmark-refresh"},
    }
    if previous is not None:
        write_json_atomic(path.with_name(path.name + ".prev"), previous)
    write_json_atomic(path, wrapper)
    result.update(status="OK", replaced=True, deepRows=len(payload["deepResults"]), cachedAt=stamp)
    return result


def main(argv: list[str]) -> int:
    country, exchange = (argv[1], argv[2]) if len(argv) >= 3 else ("DE", "XETRA")
    os.environ.setdefault("BIAP_GLOBAL_ONLINE_FIRST", "1")
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    path = _scan_cache_path(country.upper(), exchange.upper())
    try:
        with refresh_lock(path):
            outcome = refresh_benchmark(country, exchange)
            outcome["staleTempRemoved"] = cleanup_stale_temp(path)
    except RefreshLocked:
        outcome = {"country": country.upper(), "exchange": exchange.upper(), "status": "LOCKED", "replaced": False}
    log.info("refresh %s status=%s replaced=%s", exchange.upper(), outcome["status"], outcome["replaced"])
    print("BIAP_BENCHMARK_REFRESH=" + json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
