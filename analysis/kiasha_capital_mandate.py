"""Kiasha Paper capital mandates and isolated accounting.

A mandate is the explicit amount of a user's server-owned Paper cash that the
user delegates to Kiasha for a bounded period. The mandate ledger is separate
from the shared Paper position table so Kiasha performance cannot be polluted by
manual Paper trades in the same symbol.

This module never moves live money and never talks to a broker. It provides the
accounting invariants used by Auto Invest and manual-Paper guards:

* one ACTIVE/STOPPING mandate per user;
* uninvested mandate cash is reserved from manual Paper buying;
* Kiasha BUY notional cannot exceed mandate cash;
* Kiasha SELL quantity cannot exceed the mandate-owned position;
* realized P/L and positions are recorded only from mandate-tagged fills;
* STOPPING blocks new Kiasha BUYs while still allowing risk-reducing SELLs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Literal, Optional
from uuid import uuid4

from audit_store import DEFAULT_DB_PATH

Horizon = Literal["week", "month"]
_ACTIVE_STATUSES = ("ACTIVE", "STOPPING")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _duration_days(horizon: str) -> int:
    if horizon == "week":
        return 7
    if horizon == "month":
        return 30
    raise ValueError("horizon must be week or month")


class KiashaCapitalMandateStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kiasha_capital_mandates (
                    mandate_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    allocated_cash REAL NOT NULL CHECK (allocated_cash > 0),
                    mandate_cash REAL NOT NULL CHECK (mandate_cash >= 0),
                    horizon TEXT NOT NULL CHECK (horizon IN ('week','month')),
                    status TEXT NOT NULL CHECK (status IN ('ACTIVE','STOPPING','COMPLETED')),
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    stop_requested_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_user_status
                    ON kiasha_capital_mandates(user_id, status, created_at);

                CREATE TABLE IF NOT EXISTS kiasha_mandate_positions (
                    mandate_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    avg_cost REAL NOT NULL CHECK (avg_cost >= 0),
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (mandate_id, code),
                    FOREIGN KEY (mandate_id) REFERENCES kiasha_capital_mandates(mandate_id)
                );

                CREATE TABLE IF NOT EXISTS kiasha_mandate_fills (
                    fill_id TEXT PRIMARY KEY,
                    mandate_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
                    code TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    price REAL NOT NULL CHECK (price > 0),
                    notional REAL NOT NULL CHECK (notional > 0),
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, intent_id),
                    FOREIGN KEY (mandate_id) REFERENCES kiasha_capital_mandates(mandate_id)
                );
                CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_fills_mandate
                    ON kiasha_mandate_fills(mandate_id, created_at);
                """
            )

    @staticmethod
    def _mandate_payload(row: sqlite3.Row, positions: list[sqlite3.Row]) -> dict[str, Any]:
        position_items = [
            {
                "code": p["code"],
                "quantity": int(p["quantity"]),
                "avgCost": float(p["avg_cost"]),
                "costBasis": int(p["quantity"]) * float(p["avg_cost"]),
                "realizedPnL": float(p["realized_pnl"]),
                "updatedAt": p["updated_at"],
            }
            for p in positions
            if int(p["quantity"]) > 0 or abs(float(p["realized_pnl"])) > 1e-9
        ]
        invested_cost = sum(item["costBasis"] for item in position_items if item["quantity"] > 0)
        realized = sum(item["realizedPnL"] for item in position_items)
        mandate_cash = float(row["mandate_cash"])
        return {
            "mandateId": row["mandate_id"],
            "userId": row["user_id"],
            "allocatedCash": float(row["allocated_cash"]),
            "mandateCash": mandate_cash,
            "investedCost": invested_cost,
            "accountingEquityAtCost": mandate_cash + invested_cost,
            "realizedPnL": realized,
            "horizon": row["horizon"],
            "status": row["status"],
            "startsAt": row["starts_at"],
            "endsAt": row["ends_at"],
            "stopRequestedAt": row["stop_requested_at"],
            "completedAt": row["completed_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "positions": position_items,
        }

    def _load_payload(self, conn: sqlite3.Connection, mandate_id: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM kiasha_capital_mandates WHERE mandate_id=?", (mandate_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Kiasha capital mandate not found")
        positions = conn.execute(
            "SELECT * FROM kiasha_mandate_positions WHERE mandate_id=? ORDER BY code", (mandate_id,)
        ).fetchall()
        return self._mandate_payload(row, positions)

    def active_mandate(self, *, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT mandate_id FROM kiasha_capital_mandates
                   WHERE user_id=? AND status IN ('ACTIVE','STOPPING')
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._load_payload(conn, str(row["mandate_id"]))

    def create_mandate(
        self,
        *,
        user_id: str,
        allocated_cash: float,
        horizon: Horizon,
        paper_cash_balance: float,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        amount = float(allocated_cash)
        paper_cash = float(paper_cash_balance)
        if amount <= 0:
            raise ValueError("allocated Kiasha capital must be positive")
        if amount > paper_cash + 1e-9:
            raise ValueError("allocated Kiasha capital exceeds available Paper cash")
        days = _duration_days(horizon)
        current = now or _now()
        mandate_id = f"kcm_{uuid4().hex}"
        starts = _iso(current)
        ends = _iso(current + timedelta(days=days))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT mandate_id FROM kiasha_capital_mandates WHERE user_id=? AND status IN ('ACTIVE','STOPPING') LIMIT 1",
                (user_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError("user already has an active Kiasha capital mandate")
            conn.execute(
                """INSERT INTO kiasha_capital_mandates
                   (mandate_id,user_id,allocated_cash,mandate_cash,horizon,status,
                    starts_at,ends_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,'ACTIVE',?,?,?,?)""",
                (mandate_id, user_id, amount, amount, horizon, starts, ends, starts, starts),
            )
            payload = self._load_payload(conn, mandate_id)
            conn.commit()
            return payload

    def request_stop(self, *, user_id: str) -> dict[str, Any]:
        current = _iso(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT mandate_id,status FROM kiasha_capital_mandates
                   WHERE user_id=? AND status IN ('ACTIVE','STOPPING')
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError("no active Kiasha capital mandate")
            mandate_id = str(row["mandate_id"])
            if row["status"] == "ACTIVE":
                conn.execute(
                    """UPDATE kiasha_capital_mandates
                       SET status='STOPPING',stop_requested_at=?,updated_at=?
                       WHERE mandate_id=?""",
                    (current, current, mandate_id),
                )
            payload = self._load_payload(conn, mandate_id)
            conn.commit()
            return payload

    def manual_available_cash(self, *, user_id: str, paper_cash_balance: float) -> float:
        mandate = self.active_mandate(user_id=user_id)
        reserved = float(mandate["mandateCash"]) if mandate else 0.0
        return max(0.0, float(paper_cash_balance) - reserved)

    def assert_manual_buy_allowed(self, *, user_id: str, paper_cash_balance: float, cost: float) -> None:
        available = self.manual_available_cash(user_id=user_id, paper_cash_balance=paper_cash_balance)
        if float(cost) > available + 1e-9:
            raise ValueError(
                f"manual Paper BUY would use Kiasha-reserved cash; manually available cash is {available:.0f}"
            )

    def record_fill(
        self,
        *,
        user_id: str,
        intent_id: str,
        side: Literal["BUY", "SELL"],
        code: str,
        quantity: int,
        price: float,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        qty = int(quantity)
        px = float(price)
        if qty <= 0 or px <= 0:
            raise ValueError("mandate fill quantity and price must be positive")
        symbol = str(code).strip().upper()
        if not symbol:
            raise ValueError("mandate fill symbol is required")
        current = _iso(now or _now())
        notional = qty * px

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute(
                "SELECT mandate_id FROM kiasha_mandate_fills WHERE user_id=? AND intent_id=?",
                (user_id, intent_id),
            ).fetchone()
            if duplicate is not None:
                payload = self._load_payload(conn, str(duplicate["mandate_id"]))
                conn.rollback()
                return payload

            mandate = conn.execute(
                """SELECT * FROM kiasha_capital_mandates
                   WHERE user_id=? AND status IN ('ACTIVE','STOPPING')
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if mandate is None:
                raise ValueError("Kiasha Auto Invest requires an active capital mandate")
            mandate_id = str(mandate["mandate_id"])
            status = str(mandate["status"])
            mandate_cash = float(mandate["mandate_cash"])

            position = conn.execute(
                "SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",
                (mandate_id, symbol),
            ).fetchone()
            prior_qty = int(position["quantity"]) if position else 0
            prior_avg = float(position["avg_cost"]) if position else 0.0
            realized_total = float(position["realized_pnl"]) if position else 0.0
            realized_fill = 0.0

            if side == "BUY":
                if status != "ACTIVE":
                    raise ValueError("Kiasha mandate is stopping; new BUYs are blocked")
                if notional > mandate_cash + 1e-9:
                    raise ValueError("Kiasha BUY exceeds remaining mandate cash")
                new_qty = prior_qty + qty
                new_avg = ((prior_qty * prior_avg) + notional) / new_qty
                new_cash = mandate_cash - notional
            elif side == "SELL":
                if qty > prior_qty:
                    raise ValueError("Kiasha SELL exceeds mandate-owned position")
                realized_fill = (px - prior_avg) * qty
                realized_total += realized_fill
                new_qty = prior_qty - qty
                new_avg = prior_avg if new_qty > 0 else 0.0
                new_cash = mandate_cash + notional
            else:
                raise ValueError("mandate fill side must be BUY or SELL")

            conn.execute(
                """INSERT INTO kiasha_mandate_positions
                   (mandate_id,code,quantity,avg_cost,realized_pnl,updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(mandate_id,code) DO UPDATE SET
                     quantity=excluded.quantity,avg_cost=excluded.avg_cost,
                     realized_pnl=excluded.realized_pnl,updated_at=excluded.updated_at""",
                (mandate_id, symbol, new_qty, new_avg, realized_total, current),
            )
            conn.execute(
                "UPDATE kiasha_capital_mandates SET mandate_cash=?,updated_at=? WHERE mandate_id=?",
                (new_cash, current, mandate_id),
            )
            conn.execute(
                """INSERT INTO kiasha_mandate_fills
                   (fill_id,mandate_id,user_id,intent_id,side,code,quantity,price,notional,realized_pnl,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"kcf_{uuid4().hex}", mandate_id, user_id, intent_id, side, symbol, qty, px, notional, realized_fill, current),
            )
            payload = self._load_payload(conn, mandate_id)
            conn.commit()
            return payload

    def complete_if_flat(self, *, user_id: str) -> Optional[dict[str, Any]]:
        current = _iso(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT mandate_id,status FROM kiasha_capital_mandates
                   WHERE user_id=? AND status IN ('ACTIVE','STOPPING')
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            mandate_id = str(row["mandate_id"])
            open_qty = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) AS q FROM kiasha_mandate_positions WHERE mandate_id=?",
                (mandate_id,),
            ).fetchone()["q"]
            if int(open_qty) > 0:
                payload = self._load_payload(conn, mandate_id)
                conn.rollback()
                return payload
            conn.execute(
                """UPDATE kiasha_capital_mandates SET status='COMPLETED',completed_at=?,updated_at=?
                   WHERE mandate_id=?""",
                (current, current, mandate_id),
            )
            payload = self._load_payload(conn, mandate_id)
            conn.commit()
            return payload


STORE = KiashaCapitalMandateStore()
