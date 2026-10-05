"""Canonical fundamental-evidence contract for BIAP Global.

Every market/provider normalizes into ``GlobalCompany`` + ``SourceEvidence``.
This module is the single place that decides which of those sources is
*official financial-statement evidence* and serializes one canonical
fundamentals-evidence object that is identical across markets, the cache and
the API payload. The Evidence Agent, the persistent fundamentals cache and the
mobile payload all use these functions, so provider-specific field names can
never silently disagree about provenance.

Nothing here upgrades trust: vendor/public sources are never official, audit
status is only reported when a source states it, and absent metadata stays
None.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Optional

from .models import GlobalCompany, SourceEvidence

CONTRACT_VERSION = 1

# Must stay identical to the Evidence Agent's fundamental_source gate.
OFFICIAL_FUNDAMENTAL_TOKENS = ("filing", "regulatory", "xbrl", "fundamental", "financial_statement")
_NON_OFFICIAL_MARKERS = ("vendor", "public_vendor", "derived_", "manual", "user_entered", "cache_snapshot")
# Same limit as the Evidence Agent's fresh_fundamentals guard (unchanged).
MAX_OFFICIAL_PERIOD_AGE_DAYS = 550

STATUS_OFFICIAL_CURRENT = "OFFICIAL_CURRENT"
STATUS_OFFICIAL_STALE = "OFFICIAL_STALE"
STATUS_OFFICIAL_SOURCE_UNAVAILABLE = "OFFICIAL_SOURCE_UNAVAILABLE"


def is_official_fundamental_source(source: SourceEvidence) -> bool:
    kind = str(source.source_type or "").lower().replace("-", "_")
    provider = str(source.provider or "").lower()
    if any(marker in kind for marker in _NON_OFFICIAL_MARKERS) or "vendor" in provider:
        return False
    return any(token in kind for token in OFFICIAL_FUNDAMENTAL_TOKENS)


def official_fundamental_sources(company: GlobalCompany) -> list[SourceEvidence]:
    return [source for source in company.sources if is_official_fundamental_source(source)]


def _period_age_days(period: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    text = str(period or "").strip()[:10]
    if not text:
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    return max(0, (current - day).days)


def _best_official(sources: Iterable[SourceEvidence]) -> Optional[SourceEvidence]:
    rows = list(sources)
    if not rows:
        return None
    return max(rows, key=lambda s: (str(s.period_end or ""), float(s.quality or 0.0)))


def official_fundamental_status(company: GlobalCompany, *, now: Optional[datetime] = None) -> tuple[str, str]:
    """Classify official fundamentals availability with an exact reason.

    Returns ``(status, detail)``. This is a diagnostic classification only;
    it never changes whether Evidence passes.
    """
    raw = company.raw_provider_fields or {}
    best = _best_official(official_fundamental_sources(company))
    if best is not None:
        age = _period_age_days(best.period_end or company.filing_period_end, now)
        if age is not None and age > MAX_OFFICIAL_PERIOD_AGE_DAYS:
            return STATUS_OFFICIAL_STALE, f"latest official period {best.period_end} is {age} days old"
        return STATUS_OFFICIAL_CURRENT, f"{best.provider} period {best.period_end or company.filing_period_end}"
    if raw.get("fundamentals_primary_stale"):
        chain_error = raw.get("fundamentals_official_chain_error")
        return (
            STATUS_OFFICIAL_STALE,
            f"latest official period {raw.get('fundamentals_primary_period')} is "
            f"{raw.get('fundamentals_primary_age_days')} days old; newer period only from non-official source"
            + (f"; newer official source unavailable: {str(chain_error)[:220]}" if chain_error else ""),
        )
    error = raw.get("fundamentals_primary_error")
    if error:
        return STATUS_OFFICIAL_SOURCE_UNAVAILABLE, str(error)[:900]
    if raw.get("yahoo_fundamentals_supplement_only") or raw.get("fundamentals_fallback_reason"):
        return STATUS_OFFICIAL_SOURCE_UNAVAILABLE, "no official filing adapter returned data for this market/issuer"
    return STATUS_OFFICIAL_SOURCE_UNAVAILABLE, "no official financial-statement source attached"


_VALUE_FIELDS = (
    "reporting_currency", "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct", "total_assets",
    "total_liabilities", "total_equity", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow", "total_debt",
    "interest_expense", "eps",
)


def fundamental_evidence_contract(company: GlobalCompany, *, now: Optional[datetime] = None) -> dict:
    """One canonical, market-independent fundamentals-evidence object."""
    official = official_fundamental_sources(company)
    best = _best_official(official)
    non_official = [
        s for s in company.sources
        if not is_official_fundamental_source(s)
        and any(t in str(s.source_type).lower() for t in ("financial", "fundamental", "metrics"))
    ]
    shown = best or (non_official[-1] if non_official else None)
    status, detail = official_fundamental_status(company, now=now)
    period = company.filing_period_end
    age = _period_age_days(period, now)
    raw = company.raw_provider_fields or {}
    audit = str(getattr(best, "audit_status", "") or "unknown").lower() if best else "unknown"
    return {
        "contractVersion": CONTRACT_VERSION,
        "identity": {
            "ticker": company.ticker,
            "issuerName": company.name,
            "country": company.country,
            "exchange": company.exchange,
            "mic": company.mic_code,
            "isin": company.isin,
            "lei": company.lei,
        },
        "values": {field: getattr(company, field) for field in _VALUE_FIELDS},
        "reportPeriod": period,
        "filingDate": company.filing_observed_at if best is not None else None,
        "retrievedAt": raw.get("oam_retrieved_at") or raw.get("fundamentals_cached_at") or (best.observed_at if best else None),
        "fundamental_source": best.provider if best else None,
        "sourceProvider": shown.provider if shown else None,
        "sourceType": shown.source_type if shown else None,
        "sourceUrl": shown.source_url if shown else None,
        "officialDocumentId": best.source_id if best else None,
        "isOfficial": best is not None,
        "officialStatus": status,
        "officialStatusDetail": detail,
        "provenance": "official_financial_statement" if best else ("non_official_vendor" if shown else "none"),
        "sourceQuality": round(float(shown.quality), 4) if shown else None,
        "fundamentalPeriodAgeDays": age,
        "freshness": (
            "unknown" if age is None else "stale" if age > MAX_OFFICIAL_PERIOD_AGE_DAYS else "current"
        ),
        # Only when a source explicitly states it; never inferred.
        "auditStatus": audit if audit in {"audited", "unaudited"} else None,
    }
