"""Evaluate pending Kiasha recommendations from verified TSETMC daily history.

The evaluator is deliberately conservative:
- it never invents missing prices or trading sessions;
- it only uses daily sessions strictly after the recommendation date;
- an observation is evaluated only after its configured trading-day horizon;
- it rejects price paths with extreme discontinuities (corporate actions,
  identifier/scale mismatches, or corrupted history) instead of turning them
  into fake investment returns;
- failures leave observations pending for a later retry.

Run this module periodically (for example via a systemd timer) after market close.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import argparse
import json
import os
from typing import Callable, Optional

from market_data import _read_json, _resolve_tsetmc_instrument_code, tsetmc_api_base
from performance_store import PerformanceStore


DEFAULT_MAX_SINGLE_SESSION_RATIO = float(
    os.environ.get("BIAP_PERFORMANCE_MAX_SINGLE_SESSION_RATIO", "3.0")
)


@dataclass(frozen=True)
class DailyClose:
    session_date: date
    closing_price: float


@dataclass(frozen=True)
class HorizonSelection:
    target: Optional[DailyClose]
    status: str
    reason: Optional[str] = None


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


def _generated_date(generated_at: str) -> date:
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return generated.astimezone(timezone.utc).date()


def select_horizon_close(
    history: list[DailyClose], *, generated_at: str, horizon_trading_days: int
) -> Optional[DailyClose]:
    """Backward-compatible bare horizon selector used by tests/callers.

    This function only selects the Nth later session. Production evaluation uses
    ``select_evaluable_horizon_close`` below, which also checks price continuity.
    """
    if horizon_trading_days < 1:
        return None
    generated_date = _generated_date(generated_at)
    later = [item for item in history if item.session_date > generated_date]
    if len(later) < horizon_trading_days:
        return None
    return later[horizon_trading_days - 1]


def _ratio_is_continuous(a: float, b: float, max_ratio: float) -> bool:
    if a <= 0 or b <= 0 or max_ratio <= 1.0:
        return False
    ratio = b / a
    return (1.0 / max_ratio) <= ratio <= max_ratio


def select_evaluable_horizon_close(
    history: list[DailyClose],
    *,
    generated_at: str,
    horizon_trading_days: int,
    reference_price: float,
    max_single_session_ratio: float = DEFAULT_MAX_SINGLE_SESSION_RATIO,
) -> HorizonSelection:
    """Select a horizon close only when the intervening price path is coherent.

    TSETMC's raw daily series can contain mechanical discontinuities around
    corporate actions/re-openings. Historical BIAP observations also showed
    pathological start/end scale mismatches (for example 1 -> 850 and 30,000 ->
    600,000 over a five-session horizon). Treating those jumps as investment
    returns contaminates agent accuracy/return statistics.

    We therefore require the recommendation reference price to be on the same
    scale as the first later close, and every subsequent close up to the horizon
    to remain within a configurable single-session ratio. The default 3x guard is
    intentionally very permissive for ordinary price moves while still rejecting
    the orders-of-magnitude failures seen in production. Rejected paths are not
    auto-corrected or fabricated; they remain unevaluated for audit/repair.
    """
    if horizon_trading_days < 1:
        return HorizonSelection(None, "waiting", "invalid horizon")
    if reference_price <= 0:
        return HorizonSelection(None, "discontinuity", "non-positive reference price")
    if max_single_session_ratio <= 1.0:
        raise ValueError("max_single_session_ratio must be > 1")

    generated_date = _generated_date(generated_at)
    later = [item for item in history if item.session_date > generated_date]
    if len(later) < horizon_trading_days:
        return HorizonSelection(None, "waiting", "horizon not reached")

    path = later[:horizon_trading_days]
    previous = float(reference_price)
    for item in path:
        current = float(item.closing_price)
        if not _ratio_is_continuous(previous, current, max_single_session_ratio):
            ratio = current / previous if previous > 0 else float("inf")
            return HorizonSelection(
                None,
                "discontinuity",
                f"price discontinuity {previous:g}->{current:g} ratio={ratio:g} on {item.session_date.isoformat()}",
            )
        previous = current
    return HorizonSelection(path[-1], "ok")


def _observed_at_iso(session_date: date) -> str:
    return datetime.combine(session_date, time(23, 59, 59), tzinfo=timezone.utc).isoformat()


def evaluate_pending(
    store: PerformanceStore,
    *,
    history_fetcher: Callable[[str], list[DailyClose]] = fetch_daily_history,
    limit: int = 500,
    max_single_session_ratio: float = DEFAULT_MAX_SINGLE_SESSION_RATIO,
) -> dict:
    pending = store.pending_observations(limit=limit)
    summary = {
        "pending": len(pending),
        "evaluated": 0,
        "waiting": 0,
        "discontinuities": 0,
        "errors": 0,
        "items": [],
    }
    history_cache: dict[str, list[DailyClose]] = {}

    for observation in pending:
        code = str(observation["code"])
        try:
            if code not in history_cache:
                history_cache[code] = history_fetcher(code)
            horizon = int(observation["horizon_trading_days"])
            selection = select_evaluable_horizon_close(
                history_cache[code],
                generated_at=str(observation["generated_at"]),
                horizon_trading_days=horizon,
                reference_price=float(observation["reference_price"]),
                max_single_session_ratio=max_single_session_ratio,
            )
            if selection.status == "waiting":
                summary["waiting"] += 1
                summary["items"].append(
                    {"id": observation["id"], "status": "waiting", "reason": selection.reason}
                )
                continue
            if selection.status == "discontinuity":
                summary["discontinuities"] += 1
                summary["items"].append(
                    {"id": observation["id"], "status": "discontinuity", "reason": selection.reason}
                )
                continue

            target = selection.target
            assert target is not None
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
            summary["errors"] += 1
            summary["items"].append(
                {"id": observation["id"], "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate pending Kiasha recommendation observations")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--db", default=None, help="optional BIAP performance SQLite path")
    parser.add_argument(
        "--max-single-session-ratio",
        type=float,
        default=DEFAULT_MAX_SINGLE_SESSION_RATIO,
        help="reject evaluation when reference->close or adjacent closes exceed this ratio (default: %(default)s)",
    )
    args = parser.parse_args()
    store = PerformanceStore(args.db) if args.db else PerformanceStore()
    summary = evaluate_pending(
        store,
        limit=args.limit,
        max_single_session_ratio=args.max_single_session_ratio,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
