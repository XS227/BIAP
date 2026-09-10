"""Read-only QA for Kiasha paper performance results.

This utility audits evaluated recommendation outcomes before they are used in a
paper. It does not mutate the performance database. It focuses on detecting
price-scale/mapping problems that can make average signed returns nonsensical.

Checks include:
- return distribution and robust percentiles;
- start/end price ratios;
- impossible/suspicious realized-return magnitudes;
- per-agent signed-return distribution;
- top outliers with symbol, dates and prices;
- repeated scale-ratio clusters (10x/100x/1000x etc.) that may indicate a
  unit/adjustment mismatch between reference and horizon prices.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import Counter
from statistics import median
from typing import Any, Iterable

from performance_store import DEFAULT_DB_PATH


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _summary(values: Iterable[float]) -> dict[str, Any]:
    xs = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not xs:
        return {"n": 0}
    avg = sum(xs) / len(xs)
    return {
        "n": len(xs),
        "min": min(xs),
        "p01": _percentile(xs, 0.01),
        "p05": _percentile(xs, 0.05),
        "p25": _percentile(xs, 0.25),
        "median": median(xs),
        "p75": _percentile(xs, 0.75),
        "p95": _percentile(xs, 0.95),
        "p99": _percentile(xs, 0.99),
        "max": max(xs),
        "mean": avg,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100*v:.3f}%"


def _num(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.6g}"


def build_report(db_path: str, outlier_threshold: float = 1.0, top_n: int = 30) -> dict[str, Any]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"performance database not found: {db_path}")

    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute(
            """
            SELECT id, code, symbol, generated_at, reference_price, future_price,
                   realized_return, evaluated_at, horizon_trading_days,
                   trading_days_elapsed, kiasha_call, weighted_score
            FROM recommendation_observations
            WHERE evaluated_at IS NOT NULL
              AND realized_return IS NOT NULL
              AND future_price IS NOT NULL
            ORDER BY id
            """
        ))

        realized = [float(r["realized_return"]) for r in rows]
        ratios = [float(r["future_price"]) / float(r["reference_price"]) for r in rows
                  if float(r["reference_price"]) > 0]

        suspicious = []
        for r in rows:
            rr = float(r["realized_return"])
            ref = float(r["reference_price"])
            fut = float(r["future_price"])
            ratio = fut / ref if ref > 0 else None
            if abs(rr) >= outlier_threshold:
                suspicious.append({
                    "id": int(r["id"]),
                    "code": str(r["code"]),
                    "symbol": str(r["symbol"]),
                    "generatedAt": str(r["generated_at"]),
                    "evaluatedAt": str(r["evaluated_at"]),
                    "referencePrice": ref,
                    "futurePrice": fut,
                    "priceRatio": ratio,
                    "realizedReturn": rr,
                    "realizedReturnPct": 100 * rr,
                    "horizonTradingDays": int(r["horizon_trading_days"]),
                    "tradingDaysElapsed": r["trading_days_elapsed"],
                    "kiashaCall": str(r["kiasha_call"]),
                })
        suspicious.sort(key=lambda x: abs(x["realizedReturn"]), reverse=True)

        # Detect ratios close to powers of ten. These are diagnostic only; they
        # are not automatically corrected because corporate actions and bad
        # symbol mappings must be distinguished from unit mismatches first.
        scale_clusters = Counter()
        for ratio in ratios:
            if ratio <= 0:
                continue
            for power in range(-6, 7):
                target = 10.0 ** power
                # within 2% of a power-of-ten ratio
                if abs(ratio / target - 1.0) <= 0.02:
                    scale_clusters[f"~1e{power:+d}"] += 1
                    break

        agent_rows = list(conn.execute(
            """
            SELECT ao.agent, ao.vote, ao.confidence, ao.directional_correct,
                   ao.signed_realized_return, ro.id, ro.symbol,
                   ro.reference_price, ro.future_price, ro.realized_return,
                   ro.generated_at, ro.evaluated_at
            FROM agent_observations ao
            JOIN recommendation_observations ro ON ro.id = ao.observation_id
            WHERE ro.evaluated_at IS NOT NULL
              AND ao.signed_realized_return IS NOT NULL
            ORDER BY ao.agent, ro.id
            """
        ))

        per_agent: dict[str, Any] = {}
        grouped: dict[str, list[sqlite3.Row]] = {}
        for r in agent_rows:
            grouped.setdefault(str(r["agent"]), []).append(r)

        for agent, arows in sorted(grouped.items()):
            vals = [float(r["signed_realized_return"]) for r in arows]
            correct = [int(r["directional_correct"]) for r in arows if r["directional_correct"] is not None]
            top = sorted(arows, key=lambda r: abs(float(r["signed_realized_return"])), reverse=True)[:10]
            per_agent[agent] = {
                "evaluatedDirectional": len(correct),
                "directionalAccuracy": (sum(correct) / len(correct)) if correct else None,
                "signedReturn": _summary(vals),
                "signedReturnAbsGe100pct": sum(abs(v) >= 1.0 for v in vals),
                "signedReturnAbsGe500pct": sum(abs(v) >= 5.0 for v in vals),
                "topOutliers": [
                    {
                        "observationId": int(r["id"]),
                        "symbol": str(r["symbol"]),
                        "vote": float(r["vote"]),
                        "confidence": float(r["confidence"]),
                        "referencePrice": float(r["reference_price"]),
                        "futurePrice": float(r["future_price"]),
                        "realizedReturn": float(r["realized_return"]),
                        "signedRealizedReturn": float(r["signed_realized_return"]),
                        "generatedAt": str(r["generated_at"]),
                        "evaluatedAt": str(r["evaluated_at"]),
                    }
                    for r in top
                ],
            }

        severe = sum(abs(v) >= 5.0 for v in realized)
        extreme = sum(abs(v) >= 10.0 for v in realized)
        return {
            "database": os.path.abspath(db_path),
            "evaluatedRecommendations": len(rows),
            "realizedReturn": _summary(realized),
            "priceRatioFutureOverReference": _summary(ratios),
            "outlierThresholdAbsReturn": outlier_threshold,
            "outlierCounts": {
                "absReturnGeThreshold": len(suspicious),
                "absReturnGe100pct": sum(abs(v) >= 1.0 for v in realized),
                "absReturnGe500pct": severe,
                "absReturnGe1000pct": extreme,
            },
            "possiblePowerOfTenRatioClusters": dict(scale_clusters.most_common()),
            "topRecommendationOutliers": suspicious[:top_n],
            "agents": per_agent,
            "qa": {
                "returnSeriesSafeForPaper": severe == 0,
                "note": (
                    "No >=500% realized-return outliers detected." if severe == 0 else
                    "Extreme realized-return outliers exist. Do not use mean/average return in the paper until symbol/date/price-scale mapping is verified. Accuracy can be reviewed separately, but affected rows should be traced before final Results."
                ),
            },
        }
    finally:
        conn.close()


def _print_summary_block(name: str, s: dict[str, Any], percent: bool = False) -> None:
    if not s or not s.get("n"):
        print(f"{name}: no data")
        return
    fmt = _pct if percent else _num
    print(
        f"{name}: n={s['n']} mean={fmt(s['mean'])} median={fmt(s['median'])} "
        f"p05={fmt(s['p05'])} p95={fmt(s['p95'])} min={fmt(s['min'])} max={fmt(s['max'])}"
    )


def _print_human(report: dict[str, Any]) -> None:
    print("\n========== KIASHA RESULTS QA ==========")
    print("Database:", report["database"])
    print("Evaluated recommendations:", report["evaluatedRecommendations"])
    _print_summary_block("Realized return", report["realizedReturn"], percent=True)
    _print_summary_block("Future/reference price ratio", report["priceRatioFutureOverReference"])

    c = report["outlierCounts"]
    print("\n--- Outlier counts ---")
    print(f"|return| >= 100% : {c['absReturnGe100pct']}")
    print(f"|return| >= 500% : {c['absReturnGe500pct']}")
    print(f"|return| >= 1000%: {c['absReturnGe1000pct']}")

    clusters = report["possiblePowerOfTenRatioClusters"]
    print("\n--- Possible power-of-ten price-ratio clusters (±2%) ---")
    print(clusters if clusters else "none")

    print("\n--- Per-agent QA ---")
    for agent, a in report["agents"].items():
        sr = a["signedReturn"]
        print(
            f"{agent:15} n={a['evaluatedDirectional']:4} "
            f"accuracy={_pct(a['directionalAccuracy'])} "
            f"medianSigned={_pct(sr.get('median'))} meanSigned={_pct(sr.get('mean'))} "
            f"|signed|>=500%={a['signedReturnAbsGe500pct']}"
        )

    print("\n--- Top recommendation outliers ---")
    if not report["topRecommendationOutliers"]:
        print("none")
    for x in report["topRecommendationOutliers"]:
        print(
            f"id={x['id']} symbol={x['symbol']} return={x['realizedReturnPct']:.2f}% "
            f"ref={x['referencePrice']:.6g} future={x['futurePrice']:.6g} "
            f"ratio={x['priceRatio']:.6g} generated={x['generatedAt']} evaluated={x['evaluatedAt']}"
        )

    print("\n--- PAPER RETURN QA ---")
    print("SAFE FOR PAPER:", "YES" if report["qa"]["returnSeriesSafeForPaper"] else "NO")
    print(report["qa"]["note"])
    print("=======================================\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only QA for Kiasha paper performance results")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="performance SQLite database path")
    parser.add_argument("--threshold", type=float, default=1.0, help="absolute realized-return threshold for detailed outliers; 1.0 = 100%%")
    parser.add_argument("--top", type=int, default=30, help="number of recommendation outliers to print/export")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    args = parser.parse_args()

    report = build_report(args.db, outlier_threshold=max(0.0, args.threshold), top_n=max(1, args.top))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["qa"]["returnSeriesSafeForPaper"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
