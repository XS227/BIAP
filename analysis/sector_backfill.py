"""Sector mapping from TSETMC instrument identity (sector, sub-sector, paper type) for every instrument, via the existing relay.

One paced request per instrument, outside the 22:45-02:00 UTC quiet window; writes only the ``instrument_sectors`` table of market memory.
The paper type also tells shares (300/303/307/309/313) from ETFs/funds (305), rights (301) and bonds (306), which is more reliable than names.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import market_memory as mm
from price_history_backfill import in_quiet_window

_FA = str.maketrans({"ي": "ی", "ك": "ک"})
SHARE_TYPES = {"300", "303", "307", "309", "313"}
KIND_BY_PAPER_TYPE = {"305": "fund", "301": "rights", "306": "bond", "308": "option", "311": "option"}


def row_from_identity(code: str, payload: dict, now: Optional[str] = None) -> Optional[tuple]:
    ident = (payload or {}).get("instrumentIdentity") or {}
    if not ident:
        return None
    sec, sub = ident.get("sector") or {}, ident.get("subSector") or {}
    clean = lambda v: (str(v).translate(_FA).strip() or None) if v not in (None, "") else None
    return (str(code), clean(sec.get("cSecVal")), clean(sec.get("lSecVal")), clean(sub.get("cSoSecVal")), clean(sub.get("lSoSecVal")),
            clean(ident.get("yVal")), clean(ident.get("cgrValCotTitle")), now or datetime.now(timezone.utc).isoformat(timespec="seconds"))


def kind_from_paper_type(paper_type: Optional[str]) -> Optional[str]:
    if not paper_type:
        return None
    return "stock" if paper_type in SHARE_TYPES else KIND_BY_PAPER_TYPE.get(paper_type, "other")


def backfill(codes: list[str], fetch: Callable[[str], dict], *, interval: float = 1.5, sleep: Callable[[float], None] = time.sleep,
             log: Callable[[str], None] = print, only_missing: bool = True) -> dict:
    have = set(mm.sector_map()) if only_missing else set()
    todo = [c for c in codes if c not in have]
    done = failed = 0
    batch: list[tuple] = []
    for i, code in enumerate(todo):
        try:
            row = row_from_identity(code, fetch(code))
            if row:
                batch.append(row)
                done += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            log(f"{i + 1}/{len(todo)} {code}: FAILED {str(exc)[:90]}")
        if len(batch) >= 50:
            mm.save_sectors(batch); batch = []
        sleep(interval)
    if batch:
        mm.save_sectors(batch)
    return {"requested": len(codes), "skippedAlreadyMapped": len(codes) - len(todo), "done": done, "failed": failed}


def _relay_fetch(code: str) -> dict:
    import market_data
    payload, _src = market_data._tsetmc_get(f"/Instrument/GetInstrumentIdentity/{code}", timeout=40)
    return payload


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--codes", required=True, help="JSON list of InsCodes")
    ap.add_argument("--interval", type=float, default=1.5)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if in_quiet_window() and not a.force:
        print("inside the 22:45-02:00 UTC quiet window: not fetching", file=sys.stderr)
        return 75
    print(json.dumps(backfill(json.load(open(a.codes)), _relay_fetch, interval=a.interval), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
