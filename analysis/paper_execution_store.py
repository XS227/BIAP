"""Atomic persistence for Kiasha Paper-only fills.

This module updates the server-owned Paper cash/position ledger together with
order intent, Claude/risk decision, audit event and idempotency response in one
SQLite transaction. It never contacts a real broker and never enables AUTO.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
import sqlite3
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from audit_store import DEFAULT_DB_PATH
from risk import load_policy


_TSE_TZ = ZoneInfo("Asia/Tehran")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tehran_day_bounds_utc(now_utc: datetime) -> tuple[str, str]:
    """Return UTC ISO boundaries for the current Tehran calendar day."""
    local_day = now_utc.astimezone(_TSE_TZ).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=_TSE_TZ)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


class PaperExecutionStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _user_daily_paper_notional(conn: sqlite3.Connection, *, user_id: str, now_utc: datetime) -> float:
        """Sum today's successful Paper fill costs for one authenticated owner."""
        start_utc, end_utc = _tehran_day_bounds_utc(now_utc)
        rows = conn.execute(
            """
            SELECT payload_json
            FROM audit_events
            WHERE user_id = ?
              AND event_type = 'KIASHA_AI_PAPER_FILLED'
              AND created_at >= ?
              AND created_at < ?
            """,
            (user_id, start_utc, end_utc),
        ).fetchall()
        total = 0.0
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                total += max(0.0, float(payload.get("fillCost") or 0.0))
            except (TypeError, ValueError, json.JSONDecodeError):
                # Fail closed: an unreadable successful-fill record means we
                # cannot prove remaining daily capacity safely.
                return float("inf")
        return total

    def commit_buy_fill(
        self,
        *,
        user_id: str,
        code: str,
        horizon: str,
        proposal: dict[str, Any],
        risk: dict[str, Any],
        intent: dict[str, Any],
        receipt: dict[str, Any],
        reference_price: float,
        reference_source: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Atomically commit a Paper BUY fill and return the persisted response.

        Reusing the same idempotency key for the same user returns the original
        persisted response and cannot debit cash twice. The per-user daily
        notional check runs inside the same BEGIN IMMEDIATE transaction as the
        ledger mutation, so concurrent requests cannot race around the limit.
        """
        if receipt.get("broker") != "paper" or receipt.get("status") != "PAPER_FILLED":
            raise ValueError("only PAPER_FILLED receipts from PaperBroker are accepted")
        if intent.get("mode") != "paper" or intent.get("side") != "BUY":
            raise ValueError("only paper BUY intents are accepted")
        quantity = int(intent.get("quantity") or 0)
        if quantity <= 0:
            raise ValueError("paper quantity must be positive")
        price = float(reference_price)
        if price <= 0:
            raise ValueError("verified reference price must be positive")
        cost = quantity * price
        now_utc = datetime.now(timezone.utc)
        now = now_utc.isoformat()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT response_json FROM idempotency_keys
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return json.loads(existing["response_json"])

            account = conn.execute(
                "SELECT initial_cash, cash_balance, created_at FROM paper_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if account is None:
                raise ValueError("server-owned Paper account does not exist")
            cash_before = float(account["cash_balance"])
            if cost > cash_before + 1e-9:
                raise ValueError("insufficient Paper cash balance")

            policy = load_policy()
            daily_notional_before = self._user_daily_paper_notional(
                conn, user_id=user_id, now_utc=now_utc
            )
            if daily_notional_before + cost > policy.max_daily_notional + 1e-9:
                raise ValueError(
                    f"projected user Paper daily notional exceeds max {policy.max_daily_notional:.0f}"
                )

            prior = conn.execute(
                "SELECT quantity, avg_cost FROM paper_positions WHERE user_id = ? AND code = ?",
                (user_id, code.upper()),
            ).fetchone()
            prior_qty = int(prior["quantity"]) if prior else 0
            prior_avg = float(prior["avg_cost"]) if prior else 0.0
            new_qty = prior_qty + quantity
            new_avg = ((prior_qty * prior_avg) + cost) / new_qty
            cash_after = cash_before - cost

            conn.execute(
                "UPDATE paper_accounts SET cash_balance = ?, updated_at = ? WHERE user_id = ?",
                (cash_after, now, user_id),
            )
            conn.execute(
                """
                INSERT INTO paper_positions (user_id, code, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, code) DO UPDATE SET
                    quantity=excluded.quantity,
                    avg_cost=excluded.avg_cost,
                    updated_at=excluded.updated_at
                """,
                (user_id, code.upper(), new_qty, new_avg, now),
            )

            persisted_receipt = {**receipt, "status": "PAPER_FILLED"}
            conn.execute(
                """
                INSERT INTO order_intents (
                    id, user_id, code, side, quantity, limit_price, mode, status,
                    recommendation_call, recommendation_score, created_at,
                    updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent["id"], user_id, intent["code"], intent["side"], quantity,
                    intent.get("limit_price"), intent["mode"], persisted_receipt["status"],
                    intent["recommendation_call"], intent["recommendation_score"],
                    intent["created_at"], now,
                    json.dumps(persisted_receipt, ensure_ascii=False, sort_keys=True),
                ),
            )

            decision_id = f"kai_{uuid4().hex}"
            account_after = {
                "userId": user_id,
                "initialCash": float(account["initial_cash"]),
                "cashBalance": cash_after,
                "positions": [{
                    "code": code.upper(),
                    "quantity": new_qty,
                    "avgCost": new_avg,
                    "updatedAt": now,
                }],
            }
            result = {
                "allowed": True,
                "reasons": [],
                "proposal": proposal,
                "risk": risk,
                "intent": intent,
                "receipt": persisted_receipt,
                "paperExecution": True,
                "liveExecution": False,
                "dryRun": False,
                "decisionId": decision_id,
                "referencePrice": price,
                "referencePriceSource": reference_source,
                "fillCost": cost,
                "dailyNotionalBefore": daily_notional_before,
                "dailyNotionalAfter": daily_notional_before + cost,
                "dailyNotionalLimit": policy.max_daily_notional,
                "accountAfter": account_after,
            }
            conn.execute(
                """
                INSERT INTO kiasha_ai_decisions (
                    decision_id, user_id, code, horizon, allowed, dry_run,
                    reference_price, reference_source, created_at,
                    proposal_json, risk_json, result_json
                ) VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id, user_id, code, horizon, price, reference_source, now,
                    json.dumps(proposal, ensure_ascii=False, sort_keys=True),
                    json.dumps(risk, ensure_ascii=False, sort_keys=True),
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT INTO audit_events
                    (event_id, user_id, intent_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid4().hex}", user_id, intent["id"], "KIASHA_AI_PAPER_FILLED", now,
                    json.dumps({
                        "decisionId": decision_id,
                        "code": code,
                        "horizon": horizon,
                        "quantity": quantity,
                        "price": price,
                        "fillCost": cost,
                        "dailyNotionalBefore": daily_notional_before,
                        "dailyNotionalAfter": daily_notional_before + cost,
                        "dailyNotionalLimit": policy.max_daily_notional,
                        "cashBefore": cash_before,
                        "cashAfter": cash_after,
                        "broker": "paper",
                    }, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT INTO idempotency_keys
                    (user_id, idempotency_key, intent_id, response_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id, idempotency_key, intent["id"],
                    json.dumps(result, ensure_ascii=False, sort_keys=True), now,
                ),
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
