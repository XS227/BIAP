"""Persistent audit storage for BIAP execution intents.

Uses Python's built-in sqlite3 so the prototype gains durable state without
adding a dependency. The database path is configurable with BIAP_AUDIT_DB.

This store is intentionally broker-agnostic. It records intent snapshots and
append-only audit events so Paper/Approval actions survive process restarts and
can later be correlated with a real broker adapter.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Optional


DEFAULT_DB_PATH = os.environ.get(
    "BIAP_AUDIT_DB",
    os.path.join(os.path.dirname(__file__), "biap_audit.sqlite3"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS order_intents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT '',
                    code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price REAL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    recommendation_call TEXT NOT NULL,
                    recommendation_score REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL DEFAULT '',
                    intent_id TEXT,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(intent_id) REFERENCES order_intents(id)
                );

                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_events_intent
                    ON audit_events(intent_id, seq);
                CREATE INDEX IF NOT EXISTS idx_order_intents_created
                    ON order_intents(created_at);
                """
            )
            # Older databases created before ownership was added won't have
            # these columns yet; ALTER TABLE has no "IF NOT EXISTS" so check
            # first. Existing rows become '' (unowned/legacy), never another
            # user's real id. Must run before the user_id indexes below.
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(order_intents)")}
            if "user_id" not in existing_cols:
                conn.execute("ALTER TABLE order_intents ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(audit_events)")}
            if "user_id" not in existing_cols:
                conn.execute("ALTER TABLE audit_events ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_order_intents_user
                    ON order_intents(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_events_user
                    ON audit_events(user_id, seq);
                """
            )

    def save_intent(self, intent: dict[str, Any], *, user_id: str) -> None:
        now = _now_iso()
        payload = json.dumps(intent, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO order_intents (
                    id, user_id, code, side, quantity, limit_price, mode, status,
                    recommendation_call, recommendation_score, created_at,
                    updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (
                    intent["id"], user_id, intent["code"], intent["side"], intent["quantity"],
                    intent.get("limit_price"), intent["mode"], intent["status"],
                    intent["recommendation_call"], intent["recommendation_score"],
                    intent["created_at"], now, payload,
                ),
            )

    def get_intent(self, intent_id: str, *, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM order_intents WHERE id = ? AND user_id = ?",
                (intent_id, user_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_intent_any_owner(self, intent_id: str) -> Optional[tuple[str, dict[str, Any]]]:
        """Look up an intent regardless of caller ownership.

        Only for the approver path (see auth.require_approver): approving an
        order necessarily means acting on an intent owned by a *different*
        caller than the approver, so the normal ownership-scoped get_intent
        does not apply here.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, payload_json FROM order_intents WHERE id = ?",
                (intent_id,),
            ).fetchone()
        if row is None:
            return None
        return row["user_id"], json.loads(row["payload_json"])

    def list_intents(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM order_intents WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def record_event(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        user_id: str,
        intent_id: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events
                    (event_id, user_id, intent_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    user_id,
                    intent_id,
                    event_type,
                    _now_iso(),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def list_events(self, *, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, event_id, intent_id, event_type, created_at, payload_json
                FROM audit_events
                WHERE user_id = ?
                ORDER BY seq DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            {
                "seq": row["seq"],
                "eventId": row["event_id"],
                "intentId": row["intent_id"],
                "eventType": row["event_type"],
                "createdAt": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def get_idempotent_response(self, *, user_id: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT response_json FROM idempotency_keys
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
        return json.loads(row["response_json"]) if row else None

    def save_idempotent_response(
        self, *, user_id: str, idempotency_key: str, intent_id: str, response: dict[str, Any]
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO idempotency_keys
                    (user_id, idempotency_key, intent_id, response_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, idempotency_key) DO NOTHING
                """,
                (user_id, idempotency_key, intent_id, json.dumps(response, ensure_ascii=False, sort_keys=True), _now_iso()),
            )

    # Committed intent states: a real trading commitment exists, whether or
    # not a broker has actually filled it yet. APPROVED must be included here
    # -- otherwise an approval-mode intent would count toward risk limits
    # only while PENDING_APPROVAL and then silently drop out the moment it's
    # approved, letting serial approval-mode submissions bypass the daily
    # notional cap entirely.
    _COMMITTED_STATUSES = ("PAPER_FILLED", "PENDING_APPROVAL", "APPROVED")

    def submitted_notional_today(self) -> float:
        """Return committed-intent notional for the current UTC day.

        Only intents with a limit_price can contribute to notional until a live
        quote source is wired into the execution service.
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat() + "%"
        placeholders = ",".join("?" * len(self._COMMITTED_STATUSES))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT quantity, limit_price, status
                FROM order_intents
                WHERE created_at LIKE ?
                  AND status IN ({placeholders})
                  AND limit_price IS NOT NULL
                """,
                (today_prefix, *self._COMMITTED_STATUSES),
            ).fetchall()
        return float(sum(row["quantity"] * row["limit_price"] for row in rows))

    def symbol_net_position_today(self, code: str) -> float:
        """Return today's net BUY-minus-SELL quantity for `code` across
        committed intents (see _COMMITTED_STATUSES), independent of price.

        This is a paper/approval-only system with no real holdings ledger,
        so "position" here means committed order-intent quantity, not a
        verified brokerage position -- it exists to bound how much exposure
        a single symbol can accumulate through this system in one day.
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat() + "%"
        placeholders = ",".join("?" * len(self._COMMITTED_STATUSES))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT side, quantity
                FROM order_intents
                WHERE created_at LIKE ?
                  AND code = ?
                  AND status IN ({placeholders})
                """,
                (today_prefix, code.upper(), *self._COMMITTED_STATUSES),
            ).fetchall()
        net = 0.0
        for row in rows:
            net += row["quantity"] if row["side"] == "BUY" else -row["quantity"]
        return net
