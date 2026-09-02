"""Server-backed tracking for trades executed manually outside BIAP.

These records are bookkeeping only. They never alter the Paper account and
never call a live broker. The API exists so self-reported external trades are
visible across devices in Orders and Portfolio instead of living only in
AsyncStorage on one phone.

This module attaches its endpoints to ``manual_paper_routes.router``. It is
imported for side effects by ``kiasha_paper`` before ``performance_routes``
includes that router, keeping all manual-trade APIs under /performance/ai.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Literal
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from audit_store import DEFAULT_DB_PATH
from auth import require_user_id
from manual_paper_routes import router


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
            created_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            UNIQUE(user_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_manual_external_user_created
            ON manual_external_trades(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_manual_external_user_code
            ON manual_external_trades(user_id, code, created_at);
        """
    )


class ManualTradeRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    quantity: int = Field(ge=1, le=1_000_000)
    price: float = Field(gt=0)
    symbol: str = Field(default="", max_length=128)


def _trade_payload(row: sqlite3.Row) -> dict:
    side = str(row["side"])
    return {
        "id": row["id"],
        "code": row["code"],
        "symbol": row["symbol"],
        "side": side,
        "quantity": int(row["quantity"]),
        "price": float(row["price"]),
        "status": "MANUAL_TRACKED" if side == "BUY" else "MANUAL_SOLD",
        "mode": "manual",
        "created_at": row["created_at"],
        "submittedAt": row["created_at"],
        "liveExecution": False,
        "paperExecution": False,
        "note": (
            "خرید واقعی خارج از BIAP توسط کاربر ثبت شده است."
            if side == "BUY"
            else "فروش واقعی خارج از BIAP توسط کاربر ثبت شده است."
        ),
    }


def _position_payloads(rows: list[sqlite3.Row]) -> list[dict]:
    positions: dict[str, dict] = {}
    for row in rows:
        code = str(row["code"]).strip().upper()
        qty = int(row["quantity"])
        price = float(row["price"])
        side = str(row["side"])
        current = positions.get(code)
        if current is None:
            current = {
                "id": f"manualpos_{code}",
                "code": code,
                "symbol": row["symbol"] or code,
                "quantity": 0,
                "buyPrice": 0.0,
                "buyNotional": 0.0,
                "boughtAt": row["created_at"],
                "status": "OPEN",
                "source": "MANUAL_BROKER",
            }
            positions[code] = current
        current["symbol"] = row["symbol"] or current["symbol"]
        if side == "BUY":
            old_qty = int(current["quantity"])
            old_notional = float(current["buyNotional"])
            new_qty = old_qty + qty
            new_notional = old_notional + qty * price
            current["quantity"] = new_qty
            current["buyNotional"] = new_notional
            current["buyPrice"] = new_notional / new_qty if new_qty > 0 else 0.0
            if old_qty <= 0:
                current["boughtAt"] = row["created_at"]
            current["status"] = "OPEN"
            current.pop("soldAt", None)
            current.pop("sellPrice", None)
            current.pop("sellNotional", None)
        else:
            owned = int(current["quantity"])
            sold_qty = min(qty, max(0, owned))
            remaining = max(0, owned - sold_qty)
            current["quantity"] = remaining
            current["buyNotional"] = float(current["buyPrice"]) * remaining
            if remaining == 0:
                current["status"] = "SOLD"
                current["soldAt"] = row["created_at"]
                current["sellPrice"] = price
                current["sellNotional"] = sold_qty * price
    return sorted(positions.values(), key=lambda p: str(p.get("boughtAt") or ""), reverse=True)


@router.post("/manual-trades/{code}")
def create_manual_trade(
    code: str,
    req: ManualTradeRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user_id: str = Depends(require_user_id),
):
    canonical = code.strip().upper()
    if not canonical:
        raise HTTPException(status_code=400, detail="symbol code is required")
    uid = str(user_id)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM manual_external_trades WHERE user_id=? AND idempotency_key=?",
            (uid, idempotency_key),
        ).fetchone()
        if existing is not None:
            return _trade_payload(existing)
        if req.side == "SELL":
            rows = conn.execute(
                "SELECT * FROM manual_external_trades WHERE user_id=? AND code=? ORDER BY created_at ASC",
                (uid, canonical),
            ).fetchall()
            positions = _position_payloads(rows)
            owned = int(positions[0]["quantity"]) if positions else 0
            if req.quantity > owned:
                raise HTTPException(status_code=409, detail=f"manual SELL quantity {req.quantity} exceeds tracked quantity {owned}")
        trade_id = f"manual_{uuid4().hex}"
        now = _now_iso()
        conn.execute(
            """INSERT INTO manual_external_trades
               (id,user_id,code,symbol,side,quantity,price,created_at,idempotency_key)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (trade_id, uid, canonical, req.symbol.strip() or canonical, req.side, req.quantity, req.price, now, idempotency_key),
        )
        row = conn.execute("SELECT * FROM manual_external_trades WHERE id=?", (trade_id,)).fetchone()
    assert row is not None
    return _trade_payload(row)


@router.get("/manual-trades")
def list_manual_trades(
    limit: int = Query(default=200, ge=1, le=1000),
    user_id: str = Depends(require_user_id),
):
    uid = str(user_id)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM manual_external_trades WHERE user_id=? ORDER BY created_at ASC LIMIT ?",
            (uid, limit),
        ).fetchall()
    return {
        "items": [_trade_payload(row) for row in reversed(rows)],
        "positions": _position_payloads(rows),
        "liveExecution": False,
        "paperExecution": False,
        "serverOwned": True,
    }
