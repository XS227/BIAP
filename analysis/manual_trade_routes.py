"""Server-backed tracking for trades executed manually outside BIAP.

These records are bookkeeping only: they never touch Paper cash/positions and
never call a broker. They exist so self-reported external trades are available
across devices in Orders and Portfolio.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from audit_store import DEFAULT_DB_PATH
from auth import require_user_id

router = APIRouter(prefix="/ai", tags=["manual-trades"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


with _connect() as conn:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS manual_external_trades (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            code TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            UNIQUE(user_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_manual_external_user
            ON manual_external_trades(user_id, created_at);
        """
    )


class ManualTradeRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    quantity: int = Field(ge=1, le=1_000_000)
    price: float = Field(gt=0)
    symbol: str = Field(default="", max_length=128)


def _row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "code": row["code"],
        "symbol": row["symbol"],
        "side": row["side"],
        "quantity": int(row["quantity"]),
        "price": float(row["price"]),
        "status": row["status"],
        "mode": "manual",
        "created_at": row["created_at"],
        "submittedAt": row["created_at"],
        "liveExecution": False,
        "paperExecution": False,
        "note": "خرید/فروش واقعی خارج از BIAP ثبت شده؛ هیچ سفارش واقعی از این ثبت ارسال نشده است.",
    }


@router.post("/manual-trades/{code}")
def create_manual_trade(
    code: str,
    req: ManualTradeRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user_id: str = Depends(require_user_id),
):
    code = code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="symbol code is required")
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM manual_external_trades WHERE user_id=? AND idempotency_key=?",
            (str(user_id), idempotency_key),
        ).fetchone()
        if existing:
            return _row(existing)
        now = _now()
        trade_id = f"manual_{uuid4().hex}"
        conn.execute(
            """INSERT INTO manual_external_trades
               (id,user_id,code,symbol,side,quantity,price,status,created_at,idempotency_key)
               VALUES (?,?,?,?,?,?,?,'MANUAL_TRACKED',?,?)""",
            (trade_id, str(user_id), code, req.symbol.strip() or code, req.side, req.quantity, req.price, now, idempotency_key),
        )
        row = conn.execute("SELECT * FROM manual_external_trades WHERE id=?", (trade_id,)).fetchone()
    return _row(row)


@router.get("/manual-trades")
def list_manual_trades(
    limit: int = Query(default=100, ge=1, le=500),
    user_id: str = Depends(require_user_id),
):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM manual_external_trades WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
    return {"items": [_row(r) for r in rows], "liveExecution": False, "paperExecution": False}
