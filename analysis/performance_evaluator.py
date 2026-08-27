"""Evaluate pending Kiasha recommendations from verified TSETMC daily history.

The evaluator is deliberately conservative:
- it never invents missing prices or trading sessions;
- it only uses daily sessions strictly after the recommendation date;
- an observation is evaluated only after its configured trading-day horizon;
- failures leave observations pending for a later retry.

Run this module periodically (for example via a systemd timer) after market close.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import argparse
import json
from typing import Callable, Optional

from market_data import _read_json, _resolve_tsetmc_instrument_code, tsetmc_api_base
from performance_store import PerformanceStore


@dataclass(frozen=True)
class DailyClose:
    session_date: date
    closing_price: float


def _as_price(row: dict) -> Optional[float]:
    for key in ("pClosing", "pDrCotVal", "priceYesterday"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 0:
            return price
    return None


def _as_session_date(row: dict) -> Optional[date]:
    raw = row.get("dEven")
    if raw in (None, ""):
        raw = row.get("date")
    if raw in (None, ""):
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None


def parse_daily_history(payload: dict) -> list[DailyClose]:
    rows = payload.get("closingPriceDaily")
    if not isinstance(rows, list):
        return []
    by_date: dict[date, DailyClose] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        session_date = _as_session_date(row)
        price = _as_price(row)
        if session_date is None or price is None:
            continue
        by_date[session_date] = DailyClose(session_date, price)
    return sorted(by_date.values(), key=lambda item: item.session_date)


def fetch_daily_history(code: str, *, limit: int = 400, timeout: float = 12.0) -> list[DailyClose]:
    instrument_code = _resolve_tsetmc_instrument_code(code, timeout=timeout)
    if instrument_code is None:
        return []
    payload = _read_json(
        f"{tsetmc_api_base()}/ClosingPrice/GetClosingPriceDailyList/{instrument_code}/{limit}",
        timeout=timeout,
    )
    return parse_daily_history(payload)


def select_horizon_close(
    history: list[DailyClose], *, generated_at: str, horizon_trading_days: int
) -> Optional[DailyClose]:
    if horizon_trading_days < 1:
        return None
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    generated_date = generated.astimezone(timezone.utc).date()
    # Strictly later sessions avoid using any same-day close that may have been
    # known only after the recommendation was generated.
    later = [item for item in history if item.session_date > generated_date]
    if len(later) < horizon_trading_days:
        return None
    return later[horizon_trading_days - 1]


def _observed_at_iso(session_date: date) -> str:
    # End-of-day UTC marker is safely after a recommendation from an earlier
    # calendar date and represents a completed daily market observation.
    return datetime.combine(session_date, time(23, 59, 59), tzinfo=timezone.utc).isoformat()


def evaluate_pending(
    store: PerformanceStore,
    *,
    history_fetcher: Callable[[str], list[DailyClose]] = fetch_daily_history,
    limit: int = 500,
) -> dict:
    pending = store.pending_observations(limit=limit)
    summary = {"pending": len(pending), "evaluated": 0, "waiting": 0, "errors": 0, "items": []}
    history_cache: dict[str, list[DailyClose]] = {}

    for observation in pending:
        code = str(observation["code"])
        try:
            if code not in history_cache:
                history_cache[code] = history_fetcher(code)
            horizon = int(observation["horizon_trading_days"])
            target = select_horizon_close(
                history_cache[code],
                generated_at=str(observation["generated_at"]),
                horizon_trading_days=horizon,
            )
            if target is None:
                summary["waiting"] += 1
                summary["items"].append({"id": observation["id"], "status": "waiting"})
                continue
            ok = store.evaluate_observation(
                int(observation["id"]),
                future_price=target.closing_price,
                observed_at=_observed_at_iso(target.session_date),
                trading_days_elapsed=horizon,
            )
            if ok:
                summary["evaluated"] += 1
                summary["items"].append(
                    {
                        "id": observation["id"],
                        "status": "evaluated",
                        "sessionDate": target.session_date.isoformat(),
                        "futurePrice": target.closing_price,
                    }
                )
            else:
                summary["waiting"] += 1
                summary["items"].append({"id": observation["id"], "status": "waiting"})
        except Exception as exc:
            # A network/parse problem must not fabricate an outcome or abort the
            # whole batch; leave this observation pending for the next run.
            summary["errors"] += 1
            summary["items"].append(
                {"id": observation["id"], "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate pending Kiasha recommendation observations")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--db", default=None, help="optional BIAP performance SQLite path")
    args = parser.parse_args()
    store = PerformanceStore(args.db) if args.db else PerformanceStore()
    summary = evaluate_pending(store, limit=args.limit)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
