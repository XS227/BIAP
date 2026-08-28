"""Persistent audit storage for BIAP execution intents and Kiasha Paper state.

Uses Python's built-in sqlite3 so the prototype gains durable state without
adding a dependency. The database path is configurable with BIAP_AUDIT_DB.

This store is intentionally broker-agnostic. It records intent snapshots,
append-only audit events, Kiasha AI/risk decisions, and server-owned Paper
account state so Paper sizing never has to trust a client-supplied balance.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Optional
from uuid import uuid4


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

                CREATE TABLE IF NOT EXISTS kiasha_ai_decisions (
                    decision_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    reference_price REAL,
                    reference_source TEXT,
                    created_at TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    risk_json TEXT,
                    result_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_accounts (
                    user_id TEXT PRIMARY KEY,
                    initial_cash REAL NOT NULL,
                    cash_balance REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    user_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    avg_cost REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, code),
                    FOREIGN KEY(user_id) REFERENCES paper_accounts(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_events_intent
                    ON audit_events(intent_id, seq);
                CREATE INDEX IF NOT EXISTS idx_order_intents_created
                    ON order_intents(created_at);
                CREATE INDEX IF NOT EXISTS idx_kiasha_ai_decisions_user
                    ON kiasha_ai_decisions(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_kiasha_ai_decisions_code
                    ON kiasha_ai_decisions(code, created_at);
                """
            )
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

    def save_kiasha_ai_decision(
        self,
        *,
        user_id: str,
        code: str,
        horizon: str,
        proposal: dict[str, Any],
        risk: Optional[dict[str, Any]],
        result: dict[str, Any],
        reference_price: Optional[float],
        reference_source: Optional[str],
        dry_run: bool,
    ) -> str:
        """Persist an immutable Claude proposal + deterministic risk decision."""
        decision_id = f"kai_{uuid4().hex}"
        created_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kiasha_ai_decisions (
                    decision_id, user_id, code, horizon, allowed, dry_run,
                    reference_price, reference_source, created_at,
                    proposal_json, risk_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    user_id,
                    code,
                    horizon,
                    1 if result.get("allowed") else 0,
                    1 if dry_run else 0,
                    reference_price,
                    reference_source,
                    created_at,
                    json.dumps(proposal, ensure_ascii=False, sort_keys=True),
                    json.dumps(risk, ensure_ascii=False, sort_keys=True) if risk is not None else None,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT INTO audit_events
                    (event_id, user_id, intent_id, event_type, created_at, payload_json)
                VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (
                    f"evt_{uuid4().hex}",
                    user_id,
                    "KIASHA_AI_PAPER_DRY_RUN" if dry_run else "KIASHA_AI_PAPER_DECISION",
                    created_at,
                    json.dumps({
                        "decisionId": decision_id,
                        "code": code,
                        "horizon": horizon,
                        "allowed": bool(result.get("allowed")),
                        "referencePrice": reference_price,
                        "referenceSource": reference_source,
                    }, ensure_ascii=False, sort_keys=True),
                ),
            )
        return decision_id

    def list_kiasha_ai_decisions(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT decision_id, code, horizon, allowed, dry_run, reference_price,
                       reference_source, created_at, proposal_json, risk_json, result_json
                FROM kiasha_ai_decisions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            {
                "decisionId": row["decision_id"],
                "code": row["code"],
                "horizon": row["horizon"],
                "allowed": bool(row["allowed"]),
                "dryRun": bool(row["dry_run"]),
                "referencePrice": row["reference_price"],
                "referencePriceSource": row["reference_source"],
                "createdAt": row["created_at"],
                "proposal": json.loads(row["proposal_json"]),
                "risk": json.loads(row["risk_json"]) if row["risk_json"] else None,
                "result": json.loads(row["result_json"]),
            }
            for row in rows
        ]

    def ensure_paper_account(self, *, user_id: str, initial_cash: float) -> dict[str, Any]:
        """Create a server-owned Paper account once; caller cannot reset its cash."""
        initial_cash = float(initial_cash)
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_accounts (user_id, initial_cash, cash_balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, initial_cash, initial_cash, now, now),
            )
        account = self.get_paper_account(user_id=user_id)
        assert account is not None
        return account

    def get_paper_account(self, *, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, initial_cash, cash_balance, created_at, updated_at
                FROM paper_accounts WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            positions = conn.execute(
                """
                SELECT code, quantity, avg_cost, updated_at
                FROM paper_positions WHERE user_id = ? ORDER BY code
                """,
                (user_id,),
            ).fetchall()
        return {
            "userId": row["user_id"],
            "initialCash": float(row["initial_cash"]),
            "cashBalance": float(row["cash_balance"]),
            "positions": [
                {
                    "code": p["code"],
                    "quantity": int(p["quantity"]),
                    "avgCost": float(p["avg_cost"]),
                    "updatedAt": p["updated_at"],
                }
                for p in positions
            ],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def list_all_intents(self, *, status: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT user_id, payload_json FROM order_intents WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT user_id, payload_json FROM order_intents ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        results = []
        for row in rows:
            intent = json.loads(row["payload_json"])
            intent["ownerUserId"] = row["user_id"]
            results.append(intent)
        return results

    def list_all_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, event_id, user_id, intent_id, event_type, created_at, payload_json
                FROM audit_events
                ORDER BY seq DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "seq": row["seq"],
                "eventId": row["event_id"],
                "ownerUserId": row["user_id"],
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

    _COMMITTED_STATUSES = ("PAPER_FILLED", "PENDING_APPROVAL", "APPROVED")

    def submitted_notional_today(self) -> float:
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
