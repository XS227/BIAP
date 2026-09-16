"""Public scan orchestration for BIAP Global.

Non-Iran markets use the Global two-stage scanner. Iran reuses the existing
production-proven market scan as a shortlist source and then re-runs candidates
through the Global six-agent/evidence pipeline. This wrapper intentionally
avoids changing the Iran production scanner.
"""

from __future__ import annotations

from .models import GlobalCompany
from .runtime import build_registry
from .scanner import GlobalMarketScanner
from .service import analyze_company


def scan_global_market(
    *,
    country: str,
    exchange: str,
    top_n: int = 10,
    discovery_limit: int = 1000,
    deep_limit: int = 25,
) -> dict:
    country = country.strip().upper()
    exchange = exchange.strip().upper()
    if country != "IR":
        return GlobalMarketScanner().scan(
            country=country,
            exchange=exchange,
            top_n=top_n,
            discovery_limit=discovery_limit,
            deep_limit=deep_limit,
        )

    # The legacy Iran scanner exposes refresh_market_scan(), not scan_market().
    # Keep it read-only and use its verified shortlist as discovery input.
    from market_scanner import refresh_market_scan

    legacy = refresh_market_scan(force=False)
    rows = legacy.get("top10") if isinstance(legacy, dict) else []
    if not isinstance(rows, list):
        rows = []

    registry = build_registry()
    deep_results: list[dict] = []
    for row in rows[: max(top_n, deep_limit)]:
        ticker = str(row.get("symbol") or row.get("code") or "").strip()
        if not ticker:
            continue
        company = GlobalCompany(
            country="IR",
            exchange=exchange,
            currency="IRR",
            ticker=ticker,
            name=str(row.get("name") or ticker),
        )
        try:
            deep_results.append(analyze_company(company, registry=registry))
        except Exception as exc:
            deep_results.append({
                "ticker": ticker,
                "call": "NO_RECOMMENDATION",
                "score": 0.0,
                "confidence": 0.0,
                "error": str(exc)[:300],
            })

    buys = [row for row in deep_results if row.get("call") == "BUY_CANDIDATE"]
    buys.sort(
        key=lambda row: float(row.get("score") or 0.0) * float(row.get("confidence") or 0.0),
        reverse=True,
    )
    recommendations = buys[: max(1, min(int(top_n), 50))]
    return {
        "status": "IR_LEGACY_SHORTLIST" if deep_results else "NO_RECOMMENDATION",
        "country": "IR",
        "exchange": exchange,
        "requestedRecommendations": top_n,
        "recommendationCount": len(recommendations),
        "recommendations": recommendations,
        "deepResults": deep_results,
        "legacyScanner": {
            "status": legacy.get("status") if isinstance(legacy, dict) else None,
            "source": legacy.get("source") if isinstance(legacy, dict) else None,
            "universeCount": legacy.get("universeCount") if isinstance(legacy, dict) else None,
            "marketRowsScanned": legacy.get("marketRowsScanned") if isinstance(legacy, dict) else None,
            "deepAnalyzedCount": legacy.get("deepAnalyzedCount") if isinstance(legacy, dict) else None,
        },
        "notes": "Iran uses the existing verified Iran scanner for discovery and the Global evidence gates for final eligibility.",
    }
