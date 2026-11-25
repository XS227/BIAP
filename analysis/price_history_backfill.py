"""Backfill daily TSETMC closing prices (several years) into market memory, and derive the days nobody traded.

Read-only towards TSETMC (the existing relay, one request per instrument, paced). Writes only ``symbol_snapshots`` rows with
source ``tsetmc-history-backfill`` (idempotent: UNIQUE(date, symbol, source)) and the ``market_no_trading_days`` table.
Days without a row are NOT filled: a closure stays a gap and is listed in ``market_no_trading_days`` (derived from the data).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import market_memory as mm

SOURCE = "tsetmc-history-backfill"
QUIET_START, QUIET_END = (22, 45), (2, 0)  # UTC: no fetching in this window
TRADING_WEEKDAYS = (5, 6, 0, 1, 2)  # Saturday..Wednesday (Python weekday: Mon=0)


def in_quiet_window(now: Optional[datetime] = None) -> bool:
    t = (now or datetime.now(timezone.utc)).time()
    minutes = t.hour * 60 + t.minute
    return minutes >= QUIET_START[0] * 60 + QUIET_START[1] or minutes < QUIET_END[0] * 60 + QUIET_END[1]


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def iso_date(d_even: Any) -> Optional[str]:
    s = str(d_even or "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        return None


def rows_from_payload(payload: dict, symbol: str, code: str, market: Optional[str]) -> list[tuple]:
    out = []
    for r in (payload or {}).get("closingPriceDaily") or []:
        day, close, yclose = iso_date(r.get("dEven")), _num(r.get("pClosing")), _num(r.get("priceYesterday") or r.get("yClose"))
        if not day or close is None or close <= 0:
            continue  # a day without a real close is not an observation
        change = (close - yclose) / yclose * 100 if yclose else None
        keep = {k: v for k, v in r.items() if k != "insCode"}
        out.append((f"{day}T12:00:00+00:00", day, symbol, code, market, SOURCE, close, change, None, None, json.dumps(keep, ensure_ascii=False, separators=(",", ":"))))
    return out


def live_start(symbol: str) -> Optional[str]:
    """First day this symbol has a LIVE snapshot (any source but this backfill): the backfill never writes from that day on."""
    with mm._connect() as con:
        r = con.execute("SELECT MIN(observed_date) FROM symbol_snapshots WHERE symbol=? AND source!=?", (symbol, SOURCE)).fetchone()
    return r[0] if r else None


def store(rows: Iterable[tuple]) -> int:
    rows = list(rows)
    with mm._connect() as con:
        con.executemany(
            "INSERT OR IGNORE INTO symbol_snapshots (observed_at,observed_date,symbol,instrument_code,market,source,price,change_percent,pe,market_cap,raw_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
    return len(rows)


def ensure_closure_table() -> None:
    with mm._connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS market_no_trading_days (date_g TEXT PRIMARY KEY, symbols_with_rows INTEGER NOT NULL, symbols_in_sample INTEGER NOT NULL, "
                    "run_length_days INTEGER NOT NULL, derived_at TEXT NOT NULL)")
        con.commit()


def derive_no_trading_days(min_rows_per_symbol: int = 100) -> list[dict]:
    """Trading weekdays (Sat..Wed) on which none of the sampled instruments printed a close. Holidays are included
    (no official calendar is assumed); runs of 3+ consecutive days are the candidates for an extended market closure."""
    ensure_closure_table()
    with mm._connect() as con:
        sample = [r[0] for r in con.execute("SELECT symbol FROM symbol_snapshots WHERE source=? GROUP BY symbol HAVING COUNT(*)>=?", (SOURCE, min_rows_per_symbol))]
        if not sample:
            return []
        marks = ",".join("?" * len(sample))
        per_day = {r[0]: r[1] for r in con.execute(f"SELECT observed_date, COUNT(DISTINCT symbol) FROM symbol_snapshots WHERE symbol IN ({marks}) GROUP BY observed_date", sample)}
        first, last = min(per_day), max(per_day)
        d, end = date.fromisoformat(first), date.fromisoformat(last)
        closed: list[date] = []
        while d <= end:
            if d.weekday() in TRADING_WEEKDAYS and per_day.get(d.isoformat(), 0) == 0:
                closed.append(d)
            d += timedelta(days=1)
        # run length counts consecutive TRADING weekdays that were all closed
        runs: dict[date, int] = {}
        run = 0
        prev: Optional[date] = None
        closed_set = set(closed)
        d = date.fromisoformat(first)
        while d <= end:
            if d.weekday() in TRADING_WEEKDAYS:
                run = run + 1 if d in closed_set else 0
                if d in closed_set:
                    runs[d] = run
            d += timedelta(days=1)
        # make every day of a run report the run's full length
        total: dict[date, int] = {}
        for day in sorted(runs, reverse=True):
            nxt = day + timedelta(days=1)
            while nxt.weekday() not in TRADING_WEEKDAYS:
                nxt += timedelta(days=1)
            total[day] = total.get(nxt, runs[day]) if nxt in closed_set else runs[day]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out = [{"date": day.isoformat(), "symbolsWithRows": 0, "symbolsInSample": len(sample), "runLengthDays": total[day]} for day in sorted(closed)]
        con.execute("DELETE FROM market_no_trading_days")
        con.executemany("INSERT INTO market_no_trading_days VALUES (?,?,?,?,?)", [(o["date"], 0, o["symbolsInSample"], o["runLengthDays"], now) for o in out])
        con.commit()
        return out


def backfill(targets: list[dict], fetch: Callable[[str, int], dict], *, days: int = 1500, interval: float = 1.5,
             sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    """``targets``: [{symbol, code, market}]. One request per instrument; a failure is logged and the next one continues."""
    done = failed = 0
    inserted = 0
    for i, t in enumerate(targets):
        try:
            payload = fetch(t["code"], days)
            rows = rows_from_payload(payload, t["symbol"], t["code"], t.get("market"))
            cut = live_start(t["symbol"])
            if cut:
                rows = [r for r in rows if r[1] < cut]  # live snapshots own their days (they carry P/E and market cap)
            inserted += store(rows)
            done += 1
            log(f"{i + 1}/{len(targets)} {t['symbol']}: {len(rows)} rows")
        except Exception as exc:  # never abort the whole run for one instrument
            failed += 1
            log(f"{i + 1}/{len(targets)} {t['symbol']}: FAILED {str(exc)[:100]}")
        sleep(interval)
    return {"instruments": len(targets), "done": done, "failed": failed, "rowsOffered": inserted}


def _relay_fetch(code: str, days: int) -> dict:
    import market_data
    payload, _src = market_data._tsetmc_get(f"/ClosingPrice/GetClosingPriceDailyList/{code}/{days}", timeout=60)
    return payload


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", required=True, help="JSON file: [{symbol, code, market}]")
    ap.add_argument("--days", type=int, default=1500)
    ap.add_argument("--interval", type=float, default=1.5)
    ap.add_argument("--force", action="store_true", help="allow running inside 22:45-02:00 UTC")
    a = ap.parse_args(argv)
    if in_quiet_window() and not a.force:
        print("inside the 22:45-02:00 UTC quiet window: not fetching", file=sys.stderr)
        return 75
    targets = json.load(open(a.targets, encoding="utf-8"))
    print(json.dumps(backfill(targets, _relay_fetch, days=a.days, interval=a.interval), ensure_ascii=False))
    ensure_closure_table()
    closures = derive_no_trading_days()
    print(json.dumps({"noTradingDays": len(closures), "runsOf3+": sorted({c['date'] for c in closures if c['runLengthDays'] >= 3})[:40]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
