"""Persistent recommendation observations and real agent outcome statistics.

This module intentionally does *not* invent historical performance. It records
recommendations before outcomes are known and only marks them evaluated when a
later market observation is explicitly supplied after the configured trading-day
horizon. Kiasha may read these statistics once enough genuine observations exist;
until then it continues to use its labelled fallback track records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import sqlite3
from typing import Any, Optional


DEFAULT_DB_PATH = os.environ.get(
    "BIAP_PERFORMANCE_DB",
    os.path.join(os.path.dirname(__file__), "biap_performance.sqlite3"),
)
DEFAULT_HORIZON_TRADING_DAYS = int(os.environ.get("BIAP_PERFORMANCE_HORIZON", "5"))
MIN_OBSERVED_SAMPLES = int(os.environ.get("BIAP_PERFORMANCE_MIN_SAMPLES", "50"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ObservedAgentStats:
    agent: str
    evaluated_calls: int
    directional_accuracy: float
    average_realized_return: float
    return_std: float
    last_updated: str


class PerformanceStore:
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
                CREATE TABLE IF NOT EXISTS recommendation_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    code TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    reference_price REAL NOT NULL,
                    kiasha_call TEXT NOT NULL,
                    weighted_score REAL NOT NULL,
                    horizon_trading_days INTEGER NOT NULL,
                    future_price REAL,
                    realized_return REAL,
                    evaluated_at TEXT,
                    trading_days_elapsed INTEGER,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_observations (
                    observation_id INTEGER NOT NULL,
                    agent TEXT NOT NULL,
                    vote REAL NOT NULL,
                    confidence REAL NOT NULL,
                    directional_correct INTEGER,
                    signed_realized_return REAL,
                    PRIMARY KEY (observation_id, agent),
                    FOREIGN KEY(observation_id) REFERENCES recommendation_observations(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_recommendation_symbol_time
                    ON recommendation_observations(symbol, generated_at);
                CREATE INDEX IF NOT EXISTS idx_agent_observations_agent
                    ON agent_observations(agent, observation_id);
                """
            )

    @staticmethod
    def _dedupe_key(symbol: str, generated_at: str, horizon_trading_days: int) -> str:
        # One tracked recommendation per symbol per UTC date/horizon. Repeated API
        # reads must not inflate sample counts. A later trading date can create a
        # fresh observation naturally.
        day = _parse_iso(generated_at).date().isoformat()
        return f"{symbol}|{day}|h{horizon_trading_days}"

    def record_recommendation(
        self,
        *,
        code: str,
        symbol: str,
        generated_at: str,
        reference_price: Optional[float],
        kiasha_call: str,
        weighted_score: float,
        breakdown: list[dict[str, Any]],
        horizon_trading_days: int = DEFAULT_HORIZON_TRADING_DAYS,
    ) -> Optional[int]:
        if reference_price is None or reference_price <= 0:
            # A future return cannot be evaluated rigorously without a verified
            # starting price, so do not create a misleading observation.
            return None
        if horizon_trading_days < 1:
            raise ValueError("horizon_trading_days must be positive")

        dedupe_key = self._dedupe_key(symbol, generated_at, horizon_trading_days)
        payload = json.dumps(
            {
                "code": code,
                "symbol": symbol,
                "generatedAt": generated_at,
                "referencePrice": reference_price,
                "call": kiasha_call,
                "weightedScore": weighted_score,
                "breakdown": breakdown,
                "horizonTradingDays": horizon_trading_days,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO recommendation_observations (
                    dedupe_key, code, symbol, generated_at, reference_price,
                    kiasha_call, weighted_score, horizon_trading_days, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    dedupe_key,
                    code,
                    symbol,
                    generated_at,
                    float(reference_price),
                    kiasha_call,
                    float(weighted_score),
                    horizon_trading_days,
                    payload,
                ),
            )
            row = conn.execute(
                "SELECT id FROM recommendation_observations WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            observation_id = int(row["id"])
            for entry in breakdown:
                conn.execute(
                    """
                    INSERT INTO agent_observations
                        (observation_id, agent, vote, confidence)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(observation_id, agent) DO NOTHING
                    """,
                    (
                        observation_id,
                        str(entry["agent"]),
                        float(entry["vote"]),
                        float(entry["confidence"]),
                    ),
                )
        return observation_id

    def evaluate_observation(
        self,
        observation_id: int,
        *,
        future_price: Optional[float],
        observed_at: str,
        trading_days_elapsed: int,
    ) -> bool:
        if future_price is None or future_price <= 0:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM recommendation_observations WHERE id = ?",
                (observation_id,),
            ).fetchone()
            if row is None:
                return False
            if row["evaluated_at"] is not None:
                return True
            if _parse_iso(observed_at) <= _parse_iso(row["generated_at"]):
                return False
            if trading_days_elapsed < int(row["horizon_trading_days"]):
                return False

            start_price = float(row["reference_price"])
            realized_return = (float(future_price) - start_price) / start_price
            conn.execute(
                """
                UPDATE recommendation_observations
                SET future_price = ?, realized_return = ?, evaluated_at = ?,
                    trading_days_elapsed = ?
                WHERE id = ?
                """,
                (float(future_price), realized_return, observed_at, trading_days_elapsed, observation_id),
            )

            agents = conn.execute(
                "SELECT agent, vote FROM agent_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchall()
            for agent_row in agents:
                vote = float(agent_row["vote"])
                if abs(vote) < 1e-12:
                    correct = None
                    signed_return = None
                else:
                    direction = 1.0 if vote > 0 else -1.0
                    signed_return = direction * realized_return
                    correct = 1 if signed_return > 0 else 0
                conn.execute(
                    """
                    UPDATE agent_observations
                    SET directional_correct = ?, signed_realized_return = ?
                    WHERE observation_id = ? AND agent = ?
                    """,
                    (correct, signed_return, observation_id, agent_row["agent"]),
                )
        return True

    def agent_stats(self, agent: str) -> Optional[ObservedAgentStats]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ao.directional_correct, ao.signed_realized_return, ro.evaluated_at
                FROM agent_observations ao
                JOIN recommendation_observations ro ON ro.id = ao.observation_id
                WHERE ao.agent = ?
                  AND ro.evaluated_at IS NOT NULL
                  AND ao.directional_correct IS NOT NULL
                ORDER BY ro.evaluated_at
                """,
                (agent,),
            ).fetchall()
        if not rows:
            return None
        returns = [float(row["signed_realized_return"]) for row in rows]
        n = len(rows)
        accuracy = sum(int(row["directional_correct"]) for row in rows) / n
        avg_return = sum(returns) / n
        variance = sum((value - avg_return) ** 2 for value in returns) / n
        return ObservedAgentStats(
            agent=agent,
            evaluated_calls=n,
            directional_accuracy=accuracy,
            average_realized_return=avg_return,
            return_std=math.sqrt(variance),
            last_updated=str(rows[-1]["evaluated_at"]),
        )

    def pending_observations(self, limit: int = 500) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 5000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, code, symbol, generated_at, reference_price,
                       horizon_trading_days
                FROM recommendation_observations
                WHERE evaluated_at IS NULL
                ORDER BY generated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
