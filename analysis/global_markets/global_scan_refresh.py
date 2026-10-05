"""Daily full-market scan refresher for BIAP Global."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from .country_packs import COUNTRY_PACKS


def _markets() -> tuple[tuple[str, str], ...]:
    return tuple(
        (country.upper(), exchange.code.upper())
        for country, pack in COUNTRY_PACKS.items()
        if pack.enabled and country.upper() != "IR"
        for exchange in pack.exchanges
    )


def _scan_one(country: str, exchange: str, deep_limit: int) -> dict:
    # A complete registry plus full-market history can retain a meaningful
    # amount of memory. Run each exchange in a fresh interpreter so RSS is
    # returned to the OS before the next market starts. This keeps refreshes
    # reliable on the small production VPS and prevents the OOM killer from
    # terminating both the refresh and the API worker.
    timeout = max(120, int(os.environ.get("BIAP_GLOBAL_MARKET_REFRESH_TIMEOUT", "600")))
    completed = subprocess.run(
        [sys.executable, "-m", "global_markets.global_scan_refresh", "--market", country, exchange, str(deep_limit)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    marker = "BIAP_SCAN_RESULT="
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    detail = (completed.stderr or completed.stdout or "no child output").strip()[-260:]
    return {"country": country, "exchange": exchange, "status": "ERROR", "error": detail}


def _child(country: str, exchange: str, deep_limit: int) -> int:
    from .scan_service import scan_global_market

    try:
        result = scan_global_market(
            country=country,
            exchange=exchange,
            top_n=10,
            discovery_limit=5000,
            deep_limit=deep_limit,
        )
        summary = {
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
        }
    except Exception as exc:
        summary = {
            "country": country,
            "exchange": exchange,
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {str(exc)[:260]}",
        }
    print("BIAP_SCAN_RESULT=" + json.dumps(summary, sort_keys=True))
    return 0


def main() -> int:
    # Refresh every connected market. Many production markets now have their own
    # official exchange-wide sources (Euronext, Nasdaq Nordic, BME, B3) and must
    # not be skipped merely because a generic Twelve Data/EODHD credential is
    # absent. Markets without a complete source will persist a BLOCKED diagnostic
    # cache, which is exactly what Global Top should report.
    deep_limit = max(10, min(int(os.environ.get("BIAP_GLOBAL_DAILY_DEEP_LIMIT", "25")), 50))
    summaries = []
    for country, exchange in _markets():
        try:
            summaries.append(_scan_one(country, exchange, deep_limit))
        except (subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
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
    if len(sys.argv) == 5 and sys.argv[1] == "--market":
        raise SystemExit(_child(sys.argv[2], sys.argv[3], int(sys.argv[4])))
    raise SystemExit(main())
