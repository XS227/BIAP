"""Throttled background job: fetch the filings that agent requests found missing (they are served cache-only, see ``request_mode``).

    python -m global_markets.filing_backfill --market IT EURONEXT_MILAN [--max 200] [--delay 5] [--dry-run]

Walks one market's universe, and for every supported ordinary operating company without a fresh stored fundamentals copy calls the normal
(live) provider once, which writes the cache. One request at a time with a pause (``--delay``), a cap per run (``--max``), and it refuses to
run, or stops, inside the quiet window 22:45-02:00 UTC. Excluded countries (``agent_scope``) are skipped. Never run from a web request.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .agent_scope import is_excluded

QUIET_START_MIN = 22 * 60 + 45      # 22:45 UTC
QUIET_END_MIN = 2 * 60              # 02:00 UTC


def in_quiet_window(now: datetime) -> bool:
    minutes = now.hour * 60 + now.minute
    return minutes >= QUIET_START_MIN or minutes < QUIET_END_MIN


def needs_fetch(provider, company) -> bool:
    """True when no fresh stored copy exists (providers without a cache layer are always fetched)."""
    read, fresh = getattr(provider, "_read", None), getattr(provider, "_is_fresh", None)
    if not callable(read):
        return True
    payload = read(company)
    return payload is None or (callable(fresh) and not fresh(payload))


def backfill(country: str, exchange: str, *, registry=None, max_fetch: int = 200, delay: float = 5.0, dry_run: bool = False,
             now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), sleep: Callable[[float], None] = time.sleep) -> dict:
    out = {"country": country, "exchange": exchange, "listed": 0, "alreadyStored": 0, "toFetch": 0, "fetched": 0, "failed": 0, "stopped": None}
    if is_excluded(country):
        out["stopped"] = "excluded country"
        return out
    if in_quiet_window(now()):
        out["stopped"] = "quiet window 22:45-02:00 UTC"
        return out
    from .runtime import build_registry
    from .service import _supported_operating_equity
    registry = registry or build_registry()
    fundamentals = registry.fundamentals(country, exchange)
    for company in registry.universe(country, exchange).list_instruments(country=country, exchange=exchange):
        if not _supported_operating_equity(company):
            continue
        out["listed"] += 1
        if not needs_fetch(fundamentals, company):
            out["alreadyStored"] += 1
            continue
        out["toFetch"] += 1
        if dry_run:
            continue
        if out["fetched"] + out["failed"] >= max_fetch:
            out["stopped"] = f"reached --max {max_fetch}"
            continue
        if in_quiet_window(now()):
            out["stopped"] = "quiet window 22:45-02:00 UTC"
            break
        try:
            fundamentals.enrich_fundamentals(company)       # live fetch; the persistent provider writes the stored copy
            out["fetched"] += 1
        except Exception:
            out["failed"] += 1
        sleep(delay)
    return out


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--market", nargs=2, metavar=("COUNTRY", "EXCHANGE"), required=True)
    ap.add_argument("--max", type=int, default=200, dest="max_fetch")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    res = backfill(a.market[0].upper(), a.market[1].upper(), max_fetch=a.max_fetch, delay=a.delay, dry_run=a.dry_run)
    print(json.dumps(res))
    return 3 if res["stopped"] and res["stopped"].startswith("quiet") else 0


if __name__ == "__main__":
    sys.exit(main())
