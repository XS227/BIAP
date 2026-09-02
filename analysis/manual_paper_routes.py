"""Manual Kiasha Paper orders with market-close queueing.

User-initiated Paper orders may be submitted at any time. During the ordinary
TSE session they are evaluated and filled immediately. Outside the session they
are persisted as PENDING_MARKET_OPEN and the existing five-minute Kiasha timer
revalidates the signal, verified price, ownership/cash and deterministic risk
controls after the market opens before any Paper fill is committed.

This is Paper-only. No live broker path exists here and no rule can guarantee a
profit; the controls are designed to limit exposure and reject unsafe orders.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timezone
import json
import os
import sqlite3
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from audit_store import AuditStore, DEFAULT_DB_PATH
from auth import require_user_id
from company_builder import build_company_from_quote, build_company_from_symbol
from execution import build_order_intent, submit_order_intent
from kiasha import decide
from market_data import MarketDataUnavailable, find_quote
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore
from risk import evaluate_order_risk, load_policy

router = APIRouter(prefix="/ai", tags=["performance"])
AUDIT = AuditStore()
BUY_STORE = PaperExecutionStore()
SELL_STORE = PaperSellStore()
DEFAULT_PAPER_INITIAL_CASH = float(os.getenv("KIASHA_PAPER_INITIAL_CASH", "100000000"))
TZ = ZoneInfo("Asia/Tehran")
TRADING_WEEKDAYS = {5, 6, 0, 1, 2}  # Saturday-Wednesday
MANUAL_MAX_SYMBOL_PCT = float(os.getenv("KIASHA_MANUAL_MAX_SYMBOL_PCT", "5"))
MANUAL_MIN_CASH_RESERVE_PCT = float(os.getenv("KIASHA_MANUAL_MIN_CASH_RESERVE_PCT", "30"))


class ManualPaperOrderRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    quantity: int = Field(default=10, ge=1, le=1000)


def _paper_execution_enabled() -> bool:
    return os.getenv("KIASHA_PAPER_EXECUTION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_session_open(now_utc: datetime | None = None) -> bool:
    local = (now_utc or datetime.now(timezone.utc)).astimezone(TZ)
    policy = load_policy()
    return local.weekday() in TRADING_WEEKDAYS and policy.market_session_open <= local.time().replace(tzinfo=None) <= policy.market_session_close


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_queue() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS manual_paper_queue (
                queue_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                code TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                recommendation_score REAL NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                executed_at TEXT,
                result_json TEXT,
                UNIQUE(user_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_manual_paper_queue_due
                ON manual_paper_queue(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_manual_paper_queue_user
                ON manual_paper_queue(user_id, created_at);
            """
        )


_init_queue()


def _verified_company_and_price(code: str) -> tuple[dict, float, str]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is None:
        company = build_company_from_symbol(code)
        if company is None:
            raise HTTPException(status_code=404, detail="no verified BIAP data for symbol")
        raise HTTPException(status_code=409, detail="verified current price is unavailable for Paper execution")
    company = build_company_from_quote(quote, codal_symbol=quote.name)
    raw = getattr(quote, "last_price", None) or getattr(quote, "closing_price", None)
    if raw is None or float(raw) <= 0:
        raise HTTPException(status_code=409, detail="verified current price is unavailable for Paper execution")
    return company, float(raw), "verified-market-quote"


def _position_qty(account: dict, code: str) -> int:
    target = code.strip().upper()
    for position in account.get("positions", []):
        if str(position.get("code") or "").strip().upper() == target:
            return int(position.get("quantity") or 0)
    return 0


def _sizing_capital(account: dict) -> float:
    invested = sum(float(p.get("quantity") or 0) * float(p.get("avgCost") or 0) for p in account.get("positions", []))
    return float(account.get("cashBalance") or 0) + invested


def _kiasha_account_limits(account: dict, code: str, side: str, quantity: int, price: float) -> list[str]:
    """Extra Kiasha exposure controls shared by manual Paper entries.

    These controls reduce concentration/cash-depletion risk. They do not and
    cannot promise that a market position will never lose value.
    """
    if side != "BUY":
        return []
    capital = _sizing_capital(account)
    if capital <= 0:
        return ["Paper account equity is unavailable"]
    owned = _position_qty(account, code)
    projected_symbol_value = (owned + quantity) * price
    max_symbol_value = capital * max(0.0, MANUAL_MAX_SYMBOL_PCT) / 100.0
    cash_after = float(account.get("cashBalance") or 0) - quantity * price
    min_cash = capital * max(0.0, MANUAL_MIN_CASH_RESERVE_PCT) / 100.0
    reasons: list[str] = []
    if projected_symbol_value > max_symbol_value + 1e-9:
        reasons.append(f"Kiasha symbol exposure would exceed {MANUAL_MAX_SYMBOL_PCT:.0f}% of Paper equity")
    if cash_after < min_cash - 1e-9:
        reasons.append(f"Kiasha requires at least {MANUAL_MIN_CASH_RESERVE_PCT:.0f}% Paper cash reserve")
    return reasons


def _order_payload(row: sqlite3.Row) -> dict[str, Any]:
    result = json.loads(row["result_json"]) if row["result_json"] else {}
    status = str(row["status"])
    note = {
        "PENDING_MARKET_OPEN": "بازار بسته است؛ سفارش Paper برای بازگشایی صف شد و قبل از اجرا دوباره کنترل می‌شود.",
        "CANCELLED_SIGNAL": "سیگنال کیا‌شا قبل از بازگشایی تغییر کرد؛ سفارش برای حفاظت از حساب لغو شد.",
        "CANCELLED_RISK": "کنترل ریسک در زمان بازگشایی سفارش را رد کرد.",
        "PAPER_FILLED": "سفارش Paper پس از بازگشایی و کنترل مجدد اجرا شد.",
    }.get(status, "سفارش Paper ثبت شد.")
    return {
        "id": row["queue_id"],
        "code": row["code"],
        "side": row["side"],
        "quantity": int(row["quantity"]),
        "limit_price": result.get("referencePrice"),
        "mode": "paper",
        "status": status,
        "recommendation_call": row["side"],
        "recommendation_score": float(row["recommendation_score"]),
        "created_at": row["created_at"],
        "submittedAt": row["created_at"],
        "note": note,
        "queued": status == "PENDING_MARKET_OPEN",
        "executedAt": row["executed_at"],
        "result": result,
    }


def _enqueue(*, user_id: str, code: str, side: str, quantity: int, score: float, idempotency_key: str) -> dict[str, Any]:
    now = _now_iso()
    queue_id = f"mpq_{uuid4().hex}"
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM manual_paper_queue WHERE user_id = ? AND idempotency_key = ?",
            (user_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            return _order_payload(existing)
        conn.execute(
            """INSERT INTO manual_paper_queue
               (queue_id,user_id,code,side,quantity,status,recommendation_score,idempotency_key,created_at,updated_at)
               VALUES (?,?,?,?,?,'PENDING_MARKET_OPEN',?,?,?,?)""",
            (queue_id, user_id, code.upper(), side, quantity, score, idempotency_key, now, now),
        )
        row = conn.execute("SELECT * FROM manual_paper_queue WHERE queue_id = ?", (queue_id,)).fetchone()
    assert row is not None
    return _order_payload(row)


def _set_queue_result(queue_id: str, status: str, result: dict[str, Any]) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "UPDATE manual_paper_queue SET status=?, updated_at=?, executed_at=?, result_json=? WHERE queue_id=?",
            (status, now, now if status != "PENDING_MARKET_OPEN" else None, json.dumps(result, ensure_ascii=False, sort_keys=True), queue_id),
        )


def _execute_checked(*, user_id: str, code: str, side: str, quantity: int, idempotency_key: str, require_open: bool) -> dict[str, Any]:
    company, reference_price, reference_source = _verified_company_and_price(code)
    canonical_code = str(company.get("ticker") or code).strip().upper()
    recommendation = decide(company)
    proposal = {
        "source": "kiasha-deterministic-recommendation",
        "code": canonical_code,
        "action": recommendation.call,
        "score": float(recommendation.weighted_score),
        "executionAllowed": False,
    }
    if recommendation.call != side:
        return {"allowed": False, "reasons": [f"Kiasha signal changed to {recommendation.call}; order not executed"], "proposal": proposal, "paperExecution": False, "liveExecution": False, "manualPaper": True}

    account = AUDIT.ensure_paper_account(user_id=user_id, initial_cash=DEFAULT_PAPER_INITIAL_CASH)
    owned = _position_qty(account, canonical_code)
    if side == "SELL" and quantity > owned:
        return {"allowed": False, "reasons": [f"SELL quantity {quantity} exceeds owned Paper position {owned}"], "proposal": proposal, "paperExecution": False, "liveExecution": False, "manualPaper": True}
    account_reasons = _kiasha_account_limits(account, canonical_code, side, quantity, reference_price)
    if account_reasons:
        return {"allowed": False, "reasons": account_reasons, "proposal": proposal, "paperExecution": False, "liveExecution": False, "manualPaper": True}

    policy = load_policy() if require_open else replace(load_policy(), enforce_market_session=False)
    risk = evaluate_order_risk(
        side=side,
        quantity=quantity,
        limit_price=reference_price,
        reference_price=reference_price,
        recommendation_score=float(recommendation.weighted_score),
        daily_notional_used=0.0,
        current_symbol_position=float(owned),
        quote_fetched_at=company.get("market", {}).get("quote_fetched_at"),
        policy=policy,
    )
    if not risk.allowed:
        return {"allowed": False, "reasons": list(risk.reasons), "proposal": proposal, "risk": risk.to_dict(), "paperExecution": False, "liveExecution": False, "manualPaper": True}

    intent = build_order_intent(code=canonical_code, side=side, quantity=quantity, limit_price=reference_price, mode="paper", recommendation_call=recommendation.call, recommendation_score=float(recommendation.weighted_score))
    receipt = submit_order_intent(intent)
    kwargs = dict(user_id=user_id, code=canonical_code, horizon="manual", proposal=proposal, risk=risk.to_dict(), intent=intent, receipt=receipt, reference_price=reference_price, reference_source=reference_source, idempotency_key=idempotency_key)
    result = SELL_STORE.commit_sell_fill(**kwargs) if side == "SELL" else BUY_STORE.commit_buy_fill(**kwargs)
    result["manualPaper"] = True
    result["marketSessionGuardApplied"] = require_open
    result["liveExecution"] = False
    return result


@router.post("/manual-paper/{code}")
def manual_paper_order(
    code: str,
    req: ManualPaperOrderRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user_id: str = Depends(require_user_id),
):
    """Fill in-session; queue out-of-session and revalidate at next open."""
    if not _paper_execution_enabled():
        raise HTTPException(status_code=503, detail="Kiasha Paper execution is disabled")
    user_id = str(user_id)
    company, _price, _source = _verified_company_and_price(code)
    canonical_code = str(company.get("ticker") or code).strip().upper()
    recommendation = decide(company)
    if recommendation.call != req.side.upper():
        return {"allowed": False, "reasons": [f"Kiasha signal changed to {recommendation.call}; refresh before trading"], "paperExecution": False, "liveExecution": False, "manualPaper": True}

    if not _market_session_open():
        queued = _enqueue(user_id=user_id, code=canonical_code, side=req.side.upper(), quantity=req.quantity, score=float(recommendation.weighted_score), idempotency_key=idempotency_key)
        return {
            "allowed": True,
            "reasons": [],
            "paperExecution": False,
            "queued": True,
            "orderStatus": "PENDING_MARKET_OPEN",
            "order": queued,
            "note": queued["note"],
            "liveExecution": False,
            "manualPaper": True,
        }

    try:
        return _execute_checked(user_id=user_id, code=canonical_code, side=req.side.upper(), quantity=req.quantity, idempotency_key=idempotency_key, require_open=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/manual-paper-orders")
def manual_paper_orders(
    limit: int = Query(default=100, ge=1, le=500),
    user_id: str = Depends(require_user_id),
):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM manual_paper_queue WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
    return {"items": [_order_payload(row) for row in rows], "liveExecution": False}


def process_due_manual_paper_orders(limit: int = 100) -> list[dict[str, Any]]:
    """Timer hook: process queued user orders only while TSE session is open."""
    if not _paper_execution_enabled() or not _market_session_open():
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM manual_paper_queue WHERE status='PENDING_MARKET_OPEN' ORDER BY created_at ASC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    outcomes: list[dict[str, Any]] = []
    for row in rows:
        queue_id = str(row["queue_id"])
        try:
            result = _execute_checked(
                user_id=str(row["user_id"]),
                code=str(row["code"]),
                side=str(row["side"]),
                quantity=int(row["quantity"]),
                idempotency_key=f"queue-fill:{queue_id}",
                require_open=True,
            )
            if result.get("paperExecution"):
                status = "PAPER_FILLED"
            elif any("signal changed" in str(x) for x in result.get("reasons", [])):
                status = "CANCELLED_SIGNAL"
            else:
                status = "CANCELLED_RISK"
            _set_queue_result(queue_id, status, result)
            outcomes.append({"queueId": queue_id, "status": status})
        except HTTPException as exc:
            # Data-source outages are retriable; keep the queue pending rather
            # than converting an unavailable quote into a fake fill/cancel.
            if exc.status_code in {409, 502, 503, 504}:
                outcomes.append({"queueId": queue_id, "status": "PENDING_MARKET_OPEN", "reason": str(exc.detail)[:200]})
                continue
            _set_queue_result(queue_id, "CANCELLED_RISK", {"allowed": False, "reasons": [str(exc.detail)], "paperExecution": False, "liveExecution": False})
            outcomes.append({"queueId": queue_id, "status": "CANCELLED_RISK"})
        except Exception as exc:
            outcomes.append({"queueId": queue_id, "status": "PENDING_MARKET_OPEN", "reason": str(exc)[:200]})
    return outcomes
