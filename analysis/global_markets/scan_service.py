"""Public scan orchestration for BIAP Global.

Besides single-exchange scans, this module builds a cached cross-market Top 10
across every enabled non-Iran exchange in the Global catalog. The global list
never pads results: only evidence-qualified BUY_CANDIDATE rows are ranked, and
markets without recommendation-grade evidence remain visible as excluded.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import decision_overlay
from . import investment_mode as im
from .country_packs import COUNTRY_PACKS
from .issuer import collapse_issuers
from .models import GlobalCompany
from .runtime import build_registry
from .scanner import GlobalMarketScanner
from .service import analyze_company
from .source_cache import data_root, read_json, write_json_atomic


_SCAN_CACHE_SCHEMA_VERSION = 3


def build_coverage_funnel(market_summary: list[dict], *, qualified_issuers: Optional[int] = None) -> dict:
    """Five distinct stages; a later stage is never implied by an earlier one.

    discovered -> lightweight-screened (price/market data only) -> deep-analyzed
    (full agent run on official filings) -> evidence-PASS -> qualified BUY.
    "2997/3017 screened" says nothing about how many were deeply analyzed.

    Two scopes are reported separately so numbers never mix populations:
    ``allConnectedMarkets`` (every scanned market, including ones excluded from
    ranking) and ``rankingEligibleMarkets`` (only markets whose coverage and
    fundamental-readiness gates passed; the only ones that feed Global Top).
    ``qualifiedBuy`` is a security count; ``qualifiedIssuers`` is after issuer
    de-duplication (GOOG+GOOGL = 1) and before the Top-N display cap.
    """
    def stages_for(rows: list[dict]) -> dict:
        def total(key: str) -> int:
            return sum(int(m.get(key) or 0) for m in rows)
        return {
            "markets": len(rows),
            "discovered": total("eligibleEquities"),
            "lightweightScreened": total("screenedEquities"),
            "queued": total("queued"),
            "deepAnalyzed": total("deepAnalyzed"),
            "evidencePass": total("evidencePass"),
            "coreStatementsComplete": total("coreStatementsComplete"),
            "financiallyComplete": total("financiallyComplete"),
            "qualifiedBuy": total("qualifiedBuy"),
        }

    eligible_rows = [m for m in market_summary if m.get("rankingEligible")]
    scopes = {
        "allConnectedMarkets": stages_for(market_summary),
        "rankingEligibleMarkets": stages_for(eligible_rows),
    }
    if qualified_issuers is not None:
        scopes["rankingEligibleMarkets"]["qualifiedIssuers"] = qualified_issuers
    primary = scopes["rankingEligibleMarkets"]
    discovered, screened, deep = primary["discovered"], primary["lightweightScreened"], primary["deepAnalyzed"]
    pct = lambda n: None if discovered <= 0 else round(100.0 * n / discovered, 2)
    return {
        "stages": primary,
        "scopes": scopes,
        "stagesScope": "rankingEligibleMarkets",
        "pctOfDiscovered": {
            k: pct(v) for k, v in primary.items() if k not in {"markets", "qualifiedIssuers"}
        },
        "definitions": {
            "lightweightScreened": "market-data screen only; no filing was read",
            "queued": "persistent queue: PENDING/ANALYZING companies still waiting for deep analysis (not a cap; they are analyzed in batches)",
            "deepAnalyzed": "full agent analysis completed for the company (any outcome: COMPLETE, BLOCKED or INSUFFICIENT_DATA)",
            "evidencePass": "official-filing evidence gates all cleared (data-quality gate only, NOT financial completeness)",
            "coreStatementsComplete": "revenue, operating income, net income, assets, equity and operating cash flow all present from official filings; enough for fundamental analysis even when market cap or credit ratios are unavailable",
            "financiallyComplete": "core statements and credit ratios (EBITDA, debt, interest, cash flow, valuation) all present from official sources (strict; a single unavailable ratio such as EBITDA or FFO, or a missing share count, keeps a company out)",
            "qualifiedBuy": "BUY_CANDIDATE securities with evidence PASS; still subject to portfolio constraints",
            "qualifiedIssuers": "qualified BUY after issuer de-duplication, before the Top-N display cap",
        },
        "warning": (
            "screening coverage must not be read as analysis coverage"
            if screened > 0 and deep < screened else None
        ),
    }


def _global_top_markets() -> tuple[tuple[str, str], ...]:
    """Return the complete enabled Global scan scope.

    Readiness is a result of each scheduled market scan, not a reason to omit a
    configured country. This distinction is important: omitting an unavailable
    market made coverage look better than it was and prevented its cache from
    ever being refreshed after a source or credential was connected.

    Iran stays on its separate legacy/CODAL refresh path and is therefore not
    mixed into the cross-market Global Top scan.
    """
    catalog = tuple(
        (country.upper(), exchange.code.upper())
        for country, pack in COUNTRY_PACKS.items()
        if pack.enabled and country.upper() != "IR"
        for exchange in pack.exchanges
    )
    configured = (os.environ.get("BIAP_GLOBAL_RANKING_MARKETS") or "").strip()
    if not configured:
        return catalog

    requested: list[tuple[str, str]] = []
    for item in configured.split(","):
        country, separator, exchange = item.strip().partition(":")
        if not separator or not country.strip() or not exchange.strip():
            continue
        requested.append((country.strip().upper(), exchange.strip().upper()))
    allowed = set(catalog)
    return tuple(market for market in requested if market in allowed)


def _scan_cache_path(country: str, exchange: str) -> Path:
    safe_country = "".join(ch for ch in country.upper() if ch.isalnum() or ch in {"-", "_"})
    safe_exchange = "".join(ch for ch in exchange.upper() if ch.isalnum() or ch in {"-", "_"})
    return data_root() / "scan-cache" / safe_country / f"{safe_exchange}.json"


# A phone-triggered scan must not silently change the Global Top-10 inputs: it
# may only seed a market whose scheduled artifact is missing, ineligible or
# older than this window. (Interactive scans use a bigger deepLimit, which made
# "deep-analyzed" totals jump between 391 and 591 depending on who had scanned.)
_INTERACTIVE_OVERWRITE_AFTER_HOURS = 30.0


def _artifact_age_hours(existing: object) -> Optional[float]:
    try:
        cached_at = datetime.fromisoformat(str((existing or {}).get("cachedAt") or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - cached_at.astimezone(timezone.utc)).total_seconds() / 3600.0


def _write_scan_cache(
    country: str, exchange: str, payload: dict, *, full_refresh: bool = False, origin: str = "scheduled"
) -> None:
    path = _scan_cache_path(country, exchange)
    existing = read_json(path, default=None)
    existing_payload = existing.get("payload") if isinstance(existing, dict) else None
    if origin != "scheduled" and isinstance(existing_payload, dict) and existing_payload.get("rankingEligible") is True:
        age = _artifact_age_hours(existing)
        if age is not None and age < _INTERACTIVE_OVERWRITE_AFTER_HOURS:
            return
    # Interactive/bounded scans must never replace a complete scheduled market
    # artifact.  Doing so made Global Top regress minutes after a successful
    # refresh whenever a live-check requested only a small discovery sample.
    if (
        not full_refresh
        and isinstance(existing_payload, dict)
        and existing_payload.get("rankingEligible") is True
        and payload.get("rankingEligible") is not True
    ):
        return
    wrapper = {
        "schemaVersion": _SCAN_CACHE_SCHEMA_VERSION,
        "scanOrigin": origin,
        "cachedAt": datetime.now(timezone.utc).isoformat(),
        "country": country.upper(),
        "exchange": exchange.upper(),
        "payload": payload,
    }
    rows = payload.get("deepResults") if isinstance(payload, dict) else None
    if isinstance(rows, list) and rows:
        from . import freshness

        wrapper["benchmark"] = freshness.stamp_block(
            rows, country.upper(), method="full_scan", validated_at=datetime.fromisoformat(wrapper["cachedAt"]),
            base_cached_at=wrapper["cachedAt"], quotes_as_of=freshness.quotes_as_of_of(rows))
    try:
        write_json_atomic(path, wrapper)
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
    origin: str = "interactive",
    time_budget_sec: Optional[float] = None,
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
            time_budget_sec=time_budget_sec,
        )
        result = {**result, "scanOrigin": origin, "batchLimit": deep_limit}
        _write_scan_cache(country, exchange, result, full_refresh=discovery_limit >= 5000, origin=origin)
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
    """Rank qualified candidates from fresh scheduled per-market scan artifacts.

    This function performs no network discovery or deep analysis. Expensive
    full-market work belongs to the scheduled refresh job so the mobile request
    stays fast and cannot cross the reverse-proxy timeout.
    """

    top_n = max(1, min(int(top_n), 25))
    markets = _global_top_markets()
    if im.decision_mode() == im.INVESTMENT and im.scope_restricted():
        markets = tuple(m for m in markets if im.in_scope(f"{m[0]}:{m[1]}", True))     # research scope only
    results: dict[tuple[str, str], dict] = {}

    # Global Top is a read path, never a full-market refresh path. Starting
    # exchange scans inside an HTTP request caused gateway timeouts once the
    # connected universe grew. The scheduled global_scan_refresh job is solely
    # responsible for expensive discovery/deep analysis; this endpoint consumes
    # only fresh scan artifacts and excludes missing/stale markets honestly.
    for country, exchange in markets:
        cached = _read_scan_cache(country, exchange, max_age_hours=max_age_hours)
        if cached is not None:
            results[(country, exchange)] = cached
        else:
            results[(country, exchange)] = {
                "status": "SCAN_CACHE_MISSING",
                "country": country,
                "exchange": exchange,
                "rankingEligible": False,
                "recommendations": [],
                "deepResults": [],
                "error": "Fresh daily full-market scan cache is unavailable; scheduled refresh required.",
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
        deep_rows = [r for r in (result.get("deepResults") or []) if isinstance(r, dict)]
        evidence_pass = sum(1 for r in deep_rows if (r.get("evidence") or {}).get("status") == "PASS")
        qualified_buy = sum(
            1 for r in deep_rows
            if r.get("call") == "BUY_CANDIDATE" and (r.get("evidence") or {}).get("status") == "PASS"
        )
        ledger_info = result.get("analysisLedger") if isinstance(result.get("analysisLedger"), dict) else {}
        if ledger_info:
            # the ledger covers every company; deepResults is only a capped display slice
            evidence_pass = int(ledger_info.get("evidencePass") or 0)
            qualified_buy = int(ledger_info.get("buyQualified") or 0)
        market_summary.append({
            "evidencePass": evidence_pass,
            "qualifiedBuy": qualified_buy,
            "queued": int(ledger_info.get("queued") or 0),
            "coreStatementsComplete": int(ledger_info.get("coreStatementsComplete") or 0),
            "financiallyComplete": int(ledger_info.get("financiallyComplete") or 0),
            "analysisProgressPct": ledger_info.get("progressPct"),
            "analysisByStatus": ledger_info.get("byStatus"),
            "country": country,
            "exchange": exchange,
            "status": result.get("status") or "UNKNOWN",
            "rankingEligible": ranking_eligible,
            "tiersReleased": bool(result.get("tiersReleased")),
            "recommendationCount": len(rows) if ranking_eligible else 0,
            "eligibleEquities": result.get("universeDiscovered") or 0,
            "screenedEquities": result.get("universeScreened") or 0,
            "deepAnalyzed": result.get("deepAnalyzed") or len(result.get("deepResults") or []),
            "scanOrigin": result.get("scanOrigin") or "unknown",
            "batchLimit": result.get("batchLimit"),
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

    # Company ranking is per issuer: GOOG/GOOGL (or a dual listing) is one
    # company with one risk. The other securities remain on the lead row.
    issuer_rows = collapse_issuers(
        list(deduped.values()),
        lambda row: (float(row.get("score") or 0.0) * float(row.get("confidence") or 0.0)),
    )
    ranked = sorted(
        issuer_rows,
        key=lambda row: (
            float(row.get("score") or 0.0) * float(row.get("confidence") or 0.0),
            float(row.get("confidence") or 0.0),
            float(row.get("score") or 0.0),
        ),
        reverse=True,
    )
    recommendations = []
    for row in ranked:
        if len(recommendations) >= top_n:
            break
        enriched = dict(row)
        view = decision_overlay.market_view(str(row.get("country") or ""), str(row.get("exchange") or ""))
        tier = view.get(str(row.get("ticker") or ""))
        if tier is not None:
            tier = decision_overlay.cap_for_evidence(tier, (row.get("evidence") or {}).get("status"), row.get("confidence"))
            if tier.get("insufficientEvidence"):
                continue                    # Evidence BLOCK / low confidence is not a shortlist entry
            enriched["investment"] = tier
        enriched["globalRank"] = len(recommendations) + 1
        recommendations.append(enriched)

    errors = sum(1 for row in market_summary if row["status"] == "ERROR")
    eligible_markets = sum(1 for row in market_summary if row.get("rankingEligible"))
    total_equities = sum(int(row.get("eligibleEquities") or 0) for row in market_summary)
    screened_equities = sum(int(row.get("screenedEquities") or 0) for row in market_summary)
    eligible_equities = sum(int(row.get("eligibleEquities") or 0) for row in market_summary if row.get("rankingEligible"))
    eligible_screened = sum(int(row.get("screenedEquities") or 0) for row in market_summary if row.get("rankingEligible"))
    deep_total = sum(int(row.get("deepAnalyzed") or 0) for row in market_summary if row.get("rankingEligible"))
    deep_all_markets = sum(int(row.get("deepAnalyzed") or 0) for row in market_summary)
    connected_coverage = 0.0 if total_equities <= 0 else round(100.0 * screened_equities / total_equities, 2)
    eligible_coverage = 0.0 if eligible_equities <= 0 else round(100.0 * eligible_screened / eligible_equities, 2)
    # A "market" is a country (US = NASDAQ + NYSE, DE = Xetra + Frankfurt); it is ready only when every exchange of
    # it inside the scope is ready. Exchange-level counts stay available as ``exchangesScanned`` / ``exchangesEligible``.
    by_country: dict[str, bool] = {}
    for row in market_summary:
        by_country[row["country"]] = by_country.get(row["country"], True) and bool(row.get("rankingEligible"))
    country_total = len(by_country)
    country_ready = sum(1 for ok in by_country.values() if ok)
    status = _global_scan_status(
        eligible_markets=country_ready,
        total_markets=country_total,
        recommendation_count=len(recommendations),
    )
    if eligible_markets == 0:
        recommendations = []
    funnel = build_coverage_funnel(market_summary, qualified_issuers=len(issuer_rows))
    return {
        "coverageFunnel": funnel,
        "status": status,
        "scope": "COVERAGE_QUALIFIED_GLOBAL_MARKETS",
        "refreshPolicy": "SCHEDULED_CACHE_ONLY",
        "requestedRecommendations": top_n,
        "recommendationCount": len(recommendations),
        "marketsScanned": country_total,
        "marketsEligible": country_ready,
        "marketsExcluded": country_total - country_ready,
        "exchangesScanned": len(markets),
        "exchangesEligible": eligible_markets,
        "marketErrors": errors,
        "eligibleEquities": eligible_equities,
        "screenedEquities": eligible_screened,
        "deepAnalyzed": deep_total,
        "deepAnalyzedAllMarkets": deep_all_markets,
        "qualifiedIssuers": len(issuer_rows),
        "globalCoveragePct": eligible_coverage,
        "connectedCoveragePct": connected_coverage,
        "recommendations": recommendations,
        "markets": market_summary,
        "notes": (
            "Global ranking uses only markets that pass full-market coverage and official-fundamental readiness gates. "
            "Stored or partial market records cannot enter Global Top 10. Full-market refresh runs out-of-band; user requests only read fresh scan artifacts."
        ),
    }
