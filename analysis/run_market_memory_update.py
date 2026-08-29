#!/usr/bin/env python3
"""Collect a rotating daily slice of verified market observations into Kiasha memory."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone

from market_memory import get_meta, save_symbol_snapshot, set_meta
from symbol_universe import get_symbol_universe
from tindex_data import configured as tindex_configured, fetch_symbol_overview


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _market_from_overview(payload: dict, fallback: str | None) -> str | None:
    if fallback:
        return fallback
    symbol = payload.get("symbol") if isinstance(payload, dict) else None
    raw = str((symbol or {}).get("market") or (symbol or {}).get("market_type") or "").strip().lower()
    if not raw:
        return None
    if raw in {"tse", "بورس", "بورس تهران"} or "tehran" in raw:
        return "TSE"
    if raw in {"ifb", "فرابورس"} or "farabourse" in raw or "farabors" in raw:
        return "IFB"
    return raw.upper()


def main() -> int:
    if not tindex_configured():
        print(json.dumps({"ok": False, "reason": "TINDEX_API_TOKEN missing"}, ensure_ascii=False))
        return 2

    universe = get_symbol_universe()
    if not universe:
        print(json.dumps({"ok": False, "reason": "symbol universe empty"}, ensure_ascii=False))
        return 3

    request_budget = _env_int("TINDEX_DAILY_REQUEST_BUDGET", 200, 1)
    interval = _env_float("TINDEX_REQUEST_INTERVAL_SECONDS", 1.0, 0.0)
    max_failures = _env_int("TINDEX_CONSECUTIVE_FAILURE_STOP", 3, 1)
    cursor = _env_int("BIAP_MARKET_MEMORY_CURSOR_OVERRIDE", int(get_meta("daily_cursor", "0") or 0), 0)
    cursor %= len(universe)

    attempted = saved = consecutive_failures = 0
    started = datetime.now(timezone.utc).isoformat()
    idx = cursor
    while attempted < min(request_budget, len(universe)):
        item = universe[idx]
        attempted += 1
        payload = fetch_symbol_overview(item.symbol)
        if payload:
            save_symbol_snapshot(
                symbol=item.symbol,
                source="tindex",
                payload=payload,
                instrument_code=item.code,
                market=_market_from_overview(payload, item.market),
            )
            saved += 1
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= max_failures:
                break
        idx = (idx + 1) % len(universe)
        if interval and attempted < request_budget:
            time.sleep(interval)

    set_meta("daily_cursor", str(idx))
    result = {
        "ok": saved > 0,
        "startedAt": started,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "universeSize": len(universe),
        "cursorStart": cursor,
        "cursorNext": idx,
        "attempted": attempted,
        "saved": saved,
        "stoppedAfterConsecutiveFailures": consecutive_failures >= max_failures,
        "requestBudget": request_budget,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if saved > 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
