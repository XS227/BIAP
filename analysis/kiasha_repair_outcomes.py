"""Audit and repair contaminated Kiasha performance outcomes.

Dry-run by default. With --apply this tool:
1. creates a byte-consistent SQLite backup;
2. re-fetches verified TSETMC daily history for suspicious evaluated rows;
3. revalidates the path with the same continuity guard used by the evaluator;
4. recomputes a safe outcome when possible, or invalidates the contaminated
   outcome so it no longer contributes to agent statistics;
5. writes a JSON audit report next to the database.

It never silently deletes recommendation rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import sqlite3
from typing import Any

from performance_evaluator import (
    DEFAULT_MAX_SINGLE_SESSION_RATIO,
    fetch_daily_history,
    select_evaluable_horizon_close,
)
from performance_store import DEFAULT_DB_PATH


def _iso_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup_sqlite(db_path: str, backup_path: str) -> None:
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _recompute_agents(conn: sqlite3.Connection, observation_id: int, realized_return: float) -> None:
    rows = conn.execute(
        "SELECT agent, vote FROM agent_observations WHERE observation_id = ?",
        (observation_id,),
    ).fetchall()
    for row in rows:
        vote = float(row["vote"])
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
            (correct, signed_return, observation_id, row["agent"]),
        )


def _invalidate_agents(conn: sqlite3.Connection, observation_id: int) -> None:
    conn.execute(
        """
        UPDATE agent_observations
        SET directional_correct = NULL, signed_realized_return = NULL
        WHERE observation_id = ?
        """,
        (observation_id,),
    )


def audit_and_repair(
    db_path: str,
    *,
    threshold: float = 5.0,
    max_single_session_ratio: float = DEFAULT_MAX_SINGLE_SESSION_RATIO,
    apply: bool = False,
) -> dict[str, Any]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        """
        SELECT id, code, symbol, generated_at, reference_price, future_price,
               realized_return, evaluated_at, horizon_trading_days
        FROM recommendation_observations
        WHERE evaluated_at IS NOT NULL
          AND realized_return IS NOT NULL
          AND ABS(realized_return) >= ?
        ORDER BY ABS(realized_return) DESC
        """,
        (threshold,),
    ))

    stamp = _iso_stamp()
    backup_path = None
    if apply:
        backup_path = f"{db_path}.bak-pre-kiasha-repair-{stamp}"
        _backup_sqlite(db_path, backup_path)

    history_cache: dict[str, list] = {}
    items: list[dict[str, Any]] = []
    recomputed = invalidated = unchanged = errors = 0

    try:
        for row in rows:
            item = {
                "id": int(row["id"]),
                "code": str(row["code"]),
                "symbol": str(row["symbol"]),
                "generatedAt": str(row["generated_at"]),
                "oldReferencePrice": float(row["reference_price"]),
                "oldFuturePrice": float(row["future_price"]),
                "oldRealizedReturn": float(row["realized_return"]),
            }
            try:
                code = str(row["code"])
                if code not in history_cache:
                    history_cache[code] = fetch_daily_history(code)
                selection = select_evaluable_horizon_close(
                    history_cache[code],
                    generated_at=str(row["generated_at"]),
                    horizon_trading_days=int(row["horizon_trading_days"]),
                    reference_price=float(row["reference_price"]),
                    max_single_session_ratio=max_single_session_ratio,
                )
                item["continuityStatus"] = selection.status
                item["continuityReason"] = selection.reason

                if selection.status != "ok" or selection.target is None:
                    item["action"] = "invalidate"
                    invalidated += 1
                    if apply:
                        conn.execute(
                            """
                            UPDATE recommendation_observations
                            SET future_price = NULL, realized_return = NULL,
                                evaluated_at = NULL, trading_days_elapsed = NULL
                            WHERE id = ?
                            """,
                            (row["id"],),
                        )
                        _invalidate_agents(conn, int(row["id"]))
                    items.append(item)
                    continue

                target = selection.target
                ref = float(row["reference_price"])
                new_return = (target.closing_price - ref) / ref
                item["verifiedFuturePrice"] = target.closing_price
                item["verifiedSessionDate"] = target.session_date.isoformat()
                item["verifiedRealizedReturn"] = new_return

                if (
                    abs(float(row["future_price"]) - target.closing_price) > 1e-9
                    or abs(float(row["realized_return"]) - new_return) > 1e-12
                ):
                    item["action"] = "recompute"
                    recomputed += 1
                    if apply:
                        observed_at = target.session_date.isoformat() + "T23:59:59+00:00"
                        conn.execute(
                            """
                            UPDATE recommendation_observations
                            SET future_price = ?, realized_return = ?, evaluated_at = ?,
                                trading_days_elapsed = ?
                            WHERE id = ?
                            """,
                            (
                                target.closing_price,
                                new_return,
                                observed_at,
                                int(row["horizon_trading_days"]),
                                row["id"],
                            ),
                        )
                        _recompute_agents(conn, int(row["id"]), new_return)
                else:
                    item["action"] = "unchanged_verified"
                    unchanged += 1
                items.append(item)
            except Exception as exc:
                errors += 1
                item["action"] = "error"
                item["error"] = f"{type(exc).__name__}: {exc}"
                items.append(item)

        if apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "database": os.path.abspath(db_path),
        "mode": "APPLY" if apply else "DRY_RUN",
        "backup": os.path.abspath(backup_path) if backup_path else None,
        "thresholdAbsReturn": threshold,
        "maxSingleSessionRatio": max_single_session_ratio,
        "candidates": len(rows),
        "recomputed": recomputed,
        "invalidated": invalidated,
        "unchangedVerified": unchanged,
        "errors": errors,
        "items": items,
    }

    if apply:
        audit_path = f"{db_path}.kiasha-repair-{stamp}.json"
        with open(audit_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        report["auditReport"] = os.path.abspath(audit_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/repair suspicious Kiasha outcomes")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="audit evaluated rows with absolute return >= threshold; 5.0 = 500%%",
    )
    parser.add_argument(
        "--max-single-session-ratio",
        type=float,
        default=DEFAULT_MAX_SINGLE_SESSION_RATIO,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply repairs after creating a database backup; default is dry-run",
    )
    args = parser.parse_args()
    report = audit_and_repair(
        args.db,
        threshold=max(0.0, args.threshold),
        max_single_session_ratio=args.max_single_session_ratio,
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
