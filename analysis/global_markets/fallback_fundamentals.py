"""Composable, freshness-aware fundamentals provider fallback for BIAP Global."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import os
from typing import Optional

from .models import GlobalCompany
from .providers import FundamentalsProvider, GlobalProviderError

MAX_PRIMARY_FILING_AGE_DAYS = int(
    os.environ.get("BIAP_GLOBAL_MAX_OFFICIAL_FILING_AGE_DAYS", "550")
)


def _period_date(company: GlobalCompany) -> Optional[date]:
    text = str(company.filing_period_end or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _filing_age_days(company: GlobalCompany) -> Optional[int]:
    period = _period_date(company)
    if period is None:
        return None
    return max(0, (datetime.now(timezone.utc).date() - period).days)


def _is_stale(company: GlobalCompany) -> bool:
    age = _filing_age_days(company)
    return age is not None and age > MAX_PRIMARY_FILING_AGE_DAYS


def _newer(candidate: GlobalCompany, current: GlobalCompany) -> bool:
    candidate_period = _period_date(candidate)
    current_period = _period_date(current)
    if candidate_period is None:
        return False
    if current_period is None:
        return True
    return candidate_period > current_period


class FallbackFundamentalsProvider(FundamentalsProvider):
    """Try a trusted primary source, then a labelled supplementary fallback.

    This provider is freshness-aware. A primary source that *successfully*
    returns an obsolete annual filing must not suppress a newer downstream
    source merely because no exception was raised.

    SourceEvidence remains authoritative for trust. If a newer public-vendor
    fallback replaces stale official numbers, downstream EvidenceAgent still
    BLOCKS recommendation-grade use because vendor data is not silently
    upgraded to official evidence.
    """

    def __init__(self, primary: FundamentalsProvider, fallback: FundamentalsProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_id = f"{primary.provider_id}+fallback:{fallback.provider_id}"

    @staticmethod
    def _mark(company: GlobalCompany, **fields) -> GlobalCompany:
        return replace(
            company,
            raw_provider_fields={
                **company.raw_provider_fields,
                **fields,
            },
        )

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        try:
            primary_result = self.primary.enrich_fundamentals(company)
        except GlobalProviderError as primary_error:
            try:
                enriched = self.fallback.enrich_fundamentals(company)
            except GlobalProviderError as fallback_error:
                raise GlobalProviderError(
                    f"primary fundamentals unavailable ({primary_error}); fallback unavailable ({fallback_error})"
                ) from fallback_error
            return self._mark(
                enriched,
                fundamentals_primary_error=str(primary_error)[:800],
                fundamentals_fallback_reason="primary_unavailable",
            )

        if not _is_stale(primary_result):
            return primary_result

        primary_age = _filing_age_days(primary_result)
        primary_period = primary_result.filing_period_end
        try:
            fallback_result = self.fallback.enrich_fundamentals(company)
        except GlobalProviderError as fallback_error:
            return self._mark(
                primary_result,
                fundamentals_primary_stale=True,
                fundamentals_primary_period=primary_period,
                fundamentals_primary_age_days=primary_age,
                fundamentals_stale_fallback_error=str(fallback_error)[:800],
            )

        if _newer(fallback_result, primary_result):
            # Keep the official chain's own diagnostics (e.g. why a nested
            # national-OAM source failed) so the Evidence reason stays exact.
            inner = {
                key: value for key, value in primary_result.raw_provider_fields.items()
                if key in {"fundamentals_primary_error", "fundamentals_fallback_reason"}
            }
            if inner.get("fundamentals_primary_error"):
                fallback_result = self._mark(
                    fallback_result,
                    fundamentals_official_chain_error=inner["fundamentals_primary_error"],
                )
            return self._mark(
                fallback_result,
                fundamentals_primary_stale=True,
                fundamentals_primary_period=primary_period,
                fundamentals_primary_age_days=primary_age,
                fundamentals_fallback_reason="newer_period_available",
                fundamentals_fallback_period=fallback_result.filing_period_end,
            )

        return self._mark(
            primary_result,
            fundamentals_primary_stale=True,
            fundamentals_primary_period=primary_period,
            fundamentals_primary_age_days=primary_age,
            fundamentals_fallback_reason="fallback_not_newer",
            fundamentals_fallback_period=fallback_result.filing_period_end,
        )
