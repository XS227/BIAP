"""Daily full-market scan refresher for BIAP Global."""
from __future__ import annotations

import json
import os

from .scan_service import _global_top_markets, scan_global_market


def main() -> int:
    # Refresh every connected market. Many production markets now have their own
    # official exchange-wide sources (Euronext, Nasdaq Nordic, BME, B3) and must
    # not be skipped merely because a generic Twelve Data/EODHD credential is
    # absent. Markets without a complete source will persist a BLOCKED diagnostic
    # cache, which is exactly what Global Top should report.
    deep_limit = max(10, min(int(os.environ.get("BIAP_GLOBAL_DAILY_DEEP_LIMIT", "25")), 50))
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
