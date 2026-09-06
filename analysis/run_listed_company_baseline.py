#!/usr/bin/env python3
"""Advance the persistent listed-company baseline by one bounded daily batch.

This is intentionally separate from the daily Tindex Market Memory collector:
- Market Memory keeps a small, recent Tindex observation available every day.
- This worker refreshes the heavier TSETMC/CODAL/Tindex company baseline on a
  rolling cycle. With the production default of 100 companies/day, a normal
  TSE/IFB universe is revisited roughly once per week without a single large
  CODAL burst.

Missing upstream data is recorded; it is never imputed or fabricated.
"""
from __future__ import annotations

import json
import os

from listed_company_ingestion import run_batch


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


def main() -> int:
    batch_size = _env_int("BIAP_LISTED_COMPANY_DAILY_BASELINE_BATCH", 100)
    interval = _env_float("BIAP_LISTED_COMPANY_INTERVAL_SECONDS", 2.5)
    result = run_batch(batch_size=batch_size, interval_seconds=interval)
    result = {
        **result,
        "requestedBatchSize": batch_size,
        "intervalSeconds": interval,
        "policy": "rolling weekly baseline; throttled upstream access; no fabricated values",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    # Individual upstream misses are persisted in the worker state and should
    # not make systemd retry the whole batch. Only an empty/uninitialized store
    # is treated as an operational failure.
    return 0 if int(result.get("total") or 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
