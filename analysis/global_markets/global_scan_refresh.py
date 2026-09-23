"""Daily full-market scan refresher for BIAP Global."""
from __future__ import annotations

import json
import os

from .scan_service import _global_top_markets, scan_global_market


def main() -> int:
    has_eodhd = bool((os.environ.get("BIAP_EODHD_API_TOKEN") or "").strip())
    has_twelve = bool((os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip())
    if not (has_eodhd or has_twelve):
        print("GLOBAL_SCAN_REFRESH: skipped; no full-exchange/batch market source configured")
        return 0

    deep_limit = max(10, min(int(os.environ.get("BIAP_GLOBAL_DAILY_DEEP_LIMIT", "50")), 100))
    summaries = []
    for country, exchange in _global_top_markets():
        try:
            result = scan_global_market(
                country=country,
                exchange=exchange,
                top_n=10,
                discovery_limit=5000,
                deep_limit=deep_limit,
            )
            summaries.append({
                "country": country,
                "exchange": exchange,
                "status": result.get("status"),
                "rankingEligible": result.get("rankingEligible"),
                "eligibleEquities": result.get("universeDiscovered"),
                "screenedEquities": result.get("universeScreened"),
                "marketCoveragePct": result.get("screeningCoveragePct"),
                "fundamentalCoveragePct": result.get("fundamentalCoveragePct"),
                "deepAnalyzed": result.get("deepAnalyzed"),
                "recommendationCount": result.get("recommendationCount"),
            })
        except Exception as exc:
            summaries.append({
                "country": country,
                "exchange": exchange,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {str(exc)[:260]}",
            })

    ready = sum(row.get("rankingEligible") is True for row in summaries)
    print(json.dumps({"markets": len(summaries), "ready": ready, "results": summaries}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
