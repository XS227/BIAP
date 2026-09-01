"""Daily persisted equity snapshots for server-owned Kiasha Paper accounts.

Without this, Paper "Track Record" is only ever a point-in-time unrealized
P&L computed live from the current position list -- there is no history, so
a daily/monthly return chart cannot be built. This module fills that gap:
once per day, after TSE close, it prices every open position with a verified
market quote and persists one (user, day) equity row.

Same safety rule as the rest of BIAP: a missing verified price is never
treated as zero or guessed. If any open position's price cannot be verified,
that user's snapshot for the day is skipped entirely (left for a later
retry) rather than persisting an equity figure that understates the account.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import json

from audit_store import AuditStore
from market_data import MarketDataUnavailable, find_quote

_TSE_TZ = ZoneInfo("Asia/Tehran")


def _today_tehran() -> str:
    return datetime.now(_TSE_TZ).date().isoformat()


def _position_price(code: str) -> float | None:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        return None
    if quote is None:
        return None
    candidate = quote.last_price if quote.last_price is not None else quote.closing_price
    if candidate is None or float(candidate) <= 0:
        return None
    return float(candidate)


def compute_user_equity(account: dict) -> dict:
    """Price every open position; return positionsValue=None if any price is unverified."""
    positions_value = 0.0
    unpriced: list[str] = []
    for position in account.get("positions", []):
        quantity = float(position["quantity"])
        if quantity <= 0:
            continue
        price = _position_price(str(position["code"]))
        if price is None:
            unpriced.append(str(position["code"]))
            continue
        positions_value += quantity * price
    return {
        "cashBalance": float(account["cashBalance"]),
        "positionsValue": None if unpriced else positions_value,
        "unpricedCodes": unpriced,
    }


def record_snapshot_for_all_users(store: AuditStore | None = None, *, snapshot_date: str | None = None) -> dict:
    store = store or AuditStore()
    snapshot_date = snapshot_date or _today_tehran()
    user_ids = store.list_paper_account_user_ids()
    summary = {"snapshotDate": snapshot_date, "attempted": len(user_ids), "recorded": 0, "skipped": 0, "errors": 0, "items": []}
    for user_id in user_ids:
        try:
            account = store.get_paper_account(user_id=user_id)
            if account is None:
                summary["skipped"] += 1
                summary["items"].append({"userId": user_id, "status": "skipped", "reason": "no account"})
                continue
            priced = compute_user_equity(account)
            if priced["positionsValue"] is None:
                summary["skipped"] += 1
                summary["items"].append(
                    {"userId": user_id, "status": "skipped", "reason": "unverified price", "unpricedCodes": priced["unpricedCodes"]}
                )
                continue
            snapshot = store.record_paper_equity_snapshot(
                user_id=user_id,
                snapshot_date=snapshot_date,
                cash_balance=priced["cashBalance"],
                positions_value=priced["positionsValue"],
                initial_cash=float(account["initialCash"]),
            )
            summary["recorded"] += 1
            summary["items"].append({"userId": user_id, "status": "recorded", "totalEquity": snapshot["totalEquity"]})
        except Exception as exc:
            # One user's failure must never abort the batch or fabricate their equity.
            summary["errors"] += 1
            summary["items"].append({"userId": user_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return summary


def main() -> int:
    summary = record_snapshot_for_all_users()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    # Per-user skips/errors are expected/retryable, not a run failure -- unlike
    # performance_evaluator.py, exit 0 here so systemd doesn't flag an ordinary
    # day with one unpriced symbol as a failed unit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
