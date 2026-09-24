"""Public scan orchestration for BIAP Global.

Besides single-exchange scans, this module builds a cached cross-market Top 10
for the currently finalized US/Europe/Türkiye/Brazil coverage. The global list never
pads results: only evidence-qualified BUY_CANDIDATE rows are ranked.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Optional

from .models import GlobalCompany
from .runtime import build_registry
from .scanner import GlobalMarketScanner
from .service import analyze_company
from .source_cache import data_root, read_json, write_json_atomic


_SCAN_CACHE_SCHEMA_VERSION = 3


_BASE_GLOBAL_TOP_MARKETS: tuple[tuple[str, str], ...] = (
    ("US", "NASDAQ"),
    ("US", "NYSE"),
    ("GB", "LSE"),
    ("DE", "XETRA"),
    ("FR", "EURONEXT_PARIS"),
    ("NL", "EURONEXT_AMSTERDAM"),
    ("ES", "BME_MADRID"),
    ("IT", "EURONEXT_MILAN"),
    ("SE", "NASDAQ_STOCKHOLM"),
    ("NO", "EURONEXT_OSLO"),
    ("DK", "NASDAQ_COPENHAGEN"),
    ("FI", "NASDAQ_HELSINKI"),
    ("BE", "EURONEXT_BRUSSELS"),
    ("IE", "EURONEXT_DUBLIN"),
    ("PT", "EURONEXT_LISBON"),
    ("IS", "NASDAQ_ICELAND"),
    ("TR", "BIST"),
    ("BR", "B3"),
)


def _global_top_markets() -> tuple[tuple[str, str], ...]:
    """Return markets whose official fundamentals path can currently qualify.

    Japan and South Korea are included automatically only when their regulator
    credentials are configured on the server. This keeps Global Top 10 honest:
    a market is not advertised as recommendation-capable when Evidence would be
    forced to BLOCK every stock for missing official filing provenance.
    """
    markets = list(_BASE_GLOBAL_TOP_MARKETS)
    if (os.environ.get("BIAP_EDINET_API_KEY") or "").strip():
        markets.append(("JP", "TSE_JP"))
    if (os.environ.get("BIAP_OPENDART_API_KEY") or "").strip():
        markets.append(("KR", "KRX"))
    return tuple(markets)


def _scan_cache_path(country: str, exchange: str) -> Path:
    safe_country = "".join(ch for ch in country.upper() if ch.isalnum() or ch in {"-", "_"})
    safe_exchange = "".join(ch for ch in exchange.upper() if ch.isalnum() or ch in {"-", "_"})
    return data_root() / "scan-cache" / safe_country / f"{safe_exchange}.json"


def _write_scan_cache(country: str, exchange: str, payload: dict) -> None:
    wrapper = {
        "schemaVersion": _SCAN_CACHE_SCHEMA_VERSION,
        "cachedAt": datetime.now(timezone.utc).isoformat(),
        "country": country.upper(),
        "exchange": exchange.upper(),
        "payload": payload,
    }
    try:
        write_json_atomic(_scan_cache_path(country, exchange), wrapper)
    except OSError:
        pass


def _read_scan_cache(country: str, exchange: str, *, max_age_hours: float) -> Optional[dict]:
    wrapper = read_json(_scan_cache_path(country, exchange), default=None)
    if not isinstance(wrapper, dict) or wrapper.get("schemaVersion") != _SCAN_CACHE_SCHEMA_VERSION:
        return None
    payload = wrapper.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        cached_at = datetime.fromisoformat(str(wrapper.get("cachedAt") or "").replace("Z", "+00:00"))
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - cached_at.astimezone(timezone.utc)).total_seconds() / 3600.0
    except ValueError:
        return None
    if age_hours > max(0.0, float(max_age_hours)):
        return None
    result = dict(payload)
    result["scanCache"] = {"hit": True, "cachedAt": wrapper.get("cachedAt"), "ageHours": round(max(0.0, age_hours), 2)}
    return result


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
        result = GlobalMarketScanner().scan(
            country=country,
            exchange=exchange,
            top_n=top_n,
            discovery_limit=discovery_limit,
            deep_limit=deep_limit,
        )
        _write_scan_cache(country, exchange, result)
        return result

    # Keep Iran read-only until its Tindex/CODAL integration work is explicitly
    # resumed; Global never mutates the production Iran scanner.
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


def _global_scan_status(*, eligible_markets: int, total_markets: int, recommendation_count: int) -> str:
    """Describe global scope without overstating incomplete market coverage."""
    if eligible_markets <= 0:
        return "GLOBAL_DATA_INCOMPLETE"
    if eligible_markets < total_markets:
        return "PARTIAL_GLOBAL_SCAN" if recommendation_count > 0 else "PARTIAL_GLOBAL_NO_RECOMMENDATION"
    return "GLOBAL_TOP10" if recommendation_count > 0 else "NO_RECOMMENDATION"


def scan_global_top10(
    *,
    top_n: int = 10,
    max_age_hours: float = 30.0,
) -> dict:
    """Rank qualified candidates across finalized US, Europe, Türkiye and Brazil markets.

    Per-market scans are persisted and reused for a bounded TTL. This makes the
    global view practical even before a paid all-market batch feed is enabled.
    """

    top_n = max(1, min(int(top_n), 25))
    markets = _global_top_markets()
    results: dict[tuple[str, str], dict] = {}
    pending: list[tuple[str, str]] = []

    for country, exchange in markets:
        cached = _read_scan_cache(country, exchange, max_age_hours=max_age_hours)
        if cached is not None:
            results[(country, exchange)] = cached
        else:
            pending.append((country, exchange))

    if pending:
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            future_map = {
                pool.submit(
                    scan_global_market,
                    country=country,
                    exchange=exchange,
                    top_n=5,
                    discovery_limit=5000,
                    deep_limit=50,
                ): (country, exchange)
                for country, exchange in pending
            }
            for future in as_completed(future_map):
                country, exchange = future_map[future]
                try:
                    results[(country, exchange)] = future.result()
                except Exception as exc:
                    results[(country, exchange)] = {
                        "status": "ERROR",
                        "country": country,
                        "exchange": exchange,
                        "recommendations": [],
                        "deepResults": [],
                        "error": f"{type(exc).__name__}: {str(exc)[:220]}",
                    }

    candidates: list[dict] = []
    market_summary: list[dict] = []
    for country, exchange in markets:
        result = results.get((country, exchange), {})
        rows = result.get("recommendations") if isinstance(result.get("recommendations"), list) else []
        ranking_eligible = bool(result.get("rankingEligible"))
        if ranking_eligible:
            for row in rows:
                if not isinstance(row, dict) or row.get("call") != "BUY_CANDIDATE":
                    continue
                if (row.get("evidence") or {}).get("status") != "PASS":
                    continue
                candidates.append(row)
        market_summary.append({
            "country": country,
            "exchange": exchange,
            "status": result.get("status") or "UNKNOWN",
            "rankingEligible": ranking_eligible,
            "recommendationCount": len(rows) if ranking_eligible else 0,
            "eligibleEquities": result.get("universeDiscovered") or 0,
            "screenedEquities": result.get("universeScreened") or 0,
            "deepAnalyzed": result.get("deepAnalyzed") or len(result.get("deepResults") or []),
            "screeningCoveragePct": result.get("screeningCoveragePct"),
            "fundamentalCoveragePct": result.get("fundamentalCoveragePct"),
            "dataReadiness": result.get("dataReadiness"),
            "cache": result.get("scanCache"),
            "error": result.get("error"),
        })

    deduped: dict[tuple[str, str, str], dict] = {}
    for row in candidates:
        key = (
            str(row.get("country") or "").upper(),
            str(row.get("exchange") or "").upper(),
            str(row.get("ticker") or "").upper(),
        )
        if not key[2]:
            continue
        current = deduped.get(key)
        rank = float(row.get("score") or 0.0) * float(row.get("confidence") or 0.0)
        current_rank = float(current.get("score") or 0.0) * float(current.get("confidence") or 0.0) if current else -999.0
        if current is None or rank > current_rank:
            deduped[key] = row

    ranked = sorted(
        deduped.values(),
        key=lambda row: (
            float(row.get("score") or 0.0) * float(row.get("confidence") or 0.0),
            float(row.get("confidence") or 0.0),
            float(row.get("score") or 0.0),
        ),
        reverse=True,
    )
    recommendations = []
    for index, row in enumerate(ranked[:top_n], start=1):
        enriched = dict(row)
        enriched["globalRank"] = index
        recommendations.append(enriched)

    errors = sum(1 for row in market_summary if row["status"] == "ERROR")
    eligible_markets = sum(1 for row in market_summary if row.get("rankingEligible"))
    total_equities = sum(int(row.get("eligibleEquities") or 0) for row in market_summary)
    screened_equities = sum(int(row.get("screenedEquities") or 0) for row in market_summary)
    eligible_equities = sum(int(row.get("eligibleEquities") or 0) for row in market_summary if row.get("rankingEligible"))
    eligible_screened = sum(int(row.get("screenedEquities") or 0) for row in market_summary if row.get("rankingEligible"))
    deep_total = sum(int(row.get("deepAnalyzed") or 0) for row in market_summary)
    connected_coverage = 0.0 if total_equities <= 0 else round(100.0 * screened_equities / total_equities, 2)
    eligible_coverage = 0.0 if eligible_equities <= 0 else round(100.0 * eligible_screened / eligible_equities, 2)
    status = _global_scan_status(
        eligible_markets=eligible_markets,
        total_markets=len(markets),
        recommendation_count=len(recommendations),
    )
    if eligible_markets == 0:
        recommendations = []
    return {
        "status": status,
        "scope": "COVERAGE_QUALIFIED_GLOBAL_MARKETS",
        "requestedRecommendations": top_n,
        "recommendationCount": len(recommendations),
        "marketsScanned": len(markets),
        "marketsEligible": eligible_markets,
        "marketsExcluded": len(markets) - eligible_markets,
        "marketErrors": errors,
        "eligibleEquities": eligible_equities,
        "screenedEquities": eligible_screened,
        "deepAnalyzed": deep_total,
        "globalCoveragePct": eligible_coverage,
        "connectedCoveragePct": connected_coverage,
        "recommendations": recommendations,
        "markets": market_summary,
        "notes": (
            "Global ranking uses only markets that pass full-market coverage and official-fundamental readiness gates. "
            "Stored or partial market records cannot enter Global Top 10. Cache is a short-lived performance layer, not a source of ranking eligibility."
        ),
    }
