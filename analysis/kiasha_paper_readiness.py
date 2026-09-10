"""Read-only Kiasha Paper readiness report.

This utility summarizes the real performance-tracking database without mutating it.
It is intended for paper/results readiness checks: total and evaluated
recommendations, pending outcomes, symbol coverage, date coverage, Kiasha calls,
and per-agent observed performance relative to MIN_OBSERVED_SAMPLES.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from typing import Any

from performance_store import DEFAULT_DB_PATH, MIN_OBSERVED_SAMPLES


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def build_report(db_path: str) -> dict[str, Any]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"performance database not found: {db_path}")

    # Open in SQLite read-only mode so this report cannot modify production data.
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        total = int(_scalar(conn, "SELECT COUNT(*) FROM recommendation_observations") or 0)
        evaluated = int(
            _scalar(
                conn,
                "SELECT COUNT(*) FROM recommendation_observations WHERE evaluated_at IS NOT NULL",
            )
            or 0
        )
        pending = total - evaluated
        unique_symbols = int(
            _scalar(conn, "SELECT COUNT(DISTINCT symbol) FROM recommendation_observations") or 0
        )

        calls = [
            {"call": str(row["kiasha_call"]), "count": int(row["n"])}
            for row in conn.execute(
                """
                SELECT kiasha_call, COUNT(*) AS n
                FROM recommendation_observations
                GROUP BY kiasha_call
                ORDER BY n DESC, kiasha_call
                """
            )
        ]

        by_date = [
            {
                "date": str(row["day"]),
                "total": int(row["n"]),
                "evaluated": int(row["evaluated"]),
                "pending": int(row["n"] - row["evaluated"]),
            }
            for row in conn.execute(
                """
                SELECT substr(generated_at, 1, 10) AS day,
                       COUNT(*) AS n,
                       SUM(CASE WHEN evaluated_at IS NOT NULL THEN 1 ELSE 0 END) AS evaluated
                FROM recommendation_observations
                GROUP BY day
                ORDER BY day DESC
                """
            )
        ]

        agents = []
        for row in conn.execute(
            """
            SELECT ao.agent,
                   COUNT(ao.directional_correct) AS evaluated_calls,
                   AVG(ao.directional_correct) AS directional_accuracy,
                   AVG(ao.signed_realized_return) AS average_signed_return,
                   MAX(ro.evaluated_at) AS last_updated
            FROM agent_observations ao
            JOIN recommendation_observations ro ON ro.id = ao.observation_id
            WHERE ro.evaluated_at IS NOT NULL
              AND ao.directional_correct IS NOT NULL
            GROUP BY ao.agent
            ORDER BY ao.agent
            """
        ):
            n = int(row["evaluated_calls"])
            agents.append(
                {
                    "agent": str(row["agent"]),
                    "evaluatedCalls": n,
                    "directionalAccuracy": float(row["directional_accuracy"]),
                    "averageSignedReturn": float(row["average_signed_return"]),
                    "minObservedSamples": MIN_OBSERVED_SAMPLES,
                    "readyForObservedTrackRecord": n >= MIN_OBSERVED_SAMPLES,
                    "lastUpdated": row["last_updated"],
                }
            )

        first_date = _scalar(conn, "SELECT MIN(substr(generated_at,1,10)) FROM recommendation_observations")
        last_date = _scalar(conn, "SELECT MAX(substr(generated_at,1,10)) FROM recommendation_observations")

        ready_agents = sum(1 for a in agents if a["readyForObservedTrackRecord"])
        report = {
            "database": os.path.abspath(db_path),
            "recommendations": {
                "total": total,
                "evaluated": evaluated,
                "pending": pending,
                "uniqueSymbols": unique_symbols,
                "firstObservationDate": first_date,
                "lastObservationDate": last_date,
            },
            "kiashaCalls": calls,
            "byDate": by_date,
            "agents": agents,
            "readiness": {
                "minObservedSamplesPerAgent": MIN_OBSERVED_SAMPLES,
                "agentsWithObservedTrackRecord": ready_agents,
                "agentsReported": len(agents),
                "allReportedAgentsReady": bool(agents) and ready_agents == len(agents),
                "resultsSectionCanUseObservedAgentPerformance": bool(agents)
                and ready_agents == len(agents),
            },
        }
        return report
    finally:
        conn.close()


def _print_human(report: dict[str, Any]) -> None:
    rec = report["recommendations"]
    print("\n========== KIASHA PAPER READINESS ==========")
    print(f"Database              : {report['database']}")
    print(f"Total recommendations : {rec['total']}")
    print(f"Evaluated             : {rec['evaluated']}")
    print(f"Pending               : {rec['pending']}")
    print(f"Unique symbols        : {rec['uniqueSymbols']}")
    print(f"Coverage dates        : {rec['firstObservationDate']} -> {rec['lastObservationDate']}")

    print("\n--- Calls ---")
    for item in report["kiashaCalls"]:
        print(f"{item['call']:12} {item['count']}")

    print("\n--- By date ---")
    for item in report["byDate"][:14]:
        print(
            f"{item['date']}  total={item['total']:4}  "
            f"evaluated={item['evaluated']:4}  pending={item['pending']:4}"
        )

    print("\n--- Agent evaluated performance ---")
    if not report["agents"]:
        print("No evaluated directional agent outcomes yet.")
    for item in report["agents"]:
        status = "READY" if item["readyForObservedTrackRecord"] else "WAIT"
        print(
            f"{item['agent']:15} n={item['evaluatedCalls']:4}  "
            f"accuracy={100*item['directionalAccuracy']:.2f}%  "
            f"avgSignedReturn={100*item['averageSignedReturn']:.3f}%  [{status}]"
        )

    readiness = report["readiness"]
    print("\n--- Paper readiness ---")
    print(
        "Observed-track-record agents: "
        f"{readiness['agentsWithObservedTrackRecord']}/{readiness['agentsReported']}"
    )
    print(
        "Results section ready for observed agent performance: "
        f"{'YES' if readiness['resultsSectionCanUseObservedAgentPerformance'] else 'NO'}"
    )
    print("============================================\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Kiasha Paper readiness report")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="performance SQLite database path")
    parser.add_argument("--json", action="store_true", help="print JSON instead of human-readable text")
    args = parser.parse_args()

    report = build_report(args.db)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
