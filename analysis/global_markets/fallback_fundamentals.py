"""Composable fundamentals provider fallback for BIAP Global."""
from __future__ import annotations

from .models import GlobalCompany
from .providers import FundamentalsProvider, GlobalProviderError


class FallbackFundamentalsProvider(FundamentalsProvider):
    """Try a trusted primary source, then a labelled supplementary fallback.

    The fallback provider's own SourceEvidence controls whether downstream
    verification treats the result as official filing evidence. This class does
    not upgrade source trust or invent values.
    """

    def __init__(self, primary: FundamentalsProvider, fallback: FundamentalsProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_id = f"{primary.provider_id}+fallback:{fallback.provider_id}"

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        try:
            return self.primary.enrich_fundamentals(company)
        except GlobalProviderError as primary_error:
            try:
                enriched = self.fallback.enrich_fundamentals(company)
            except GlobalProviderError as fallback_error:
                raise GlobalProviderError(
                    f"primary fundamentals unavailable ({primary_error}); fallback unavailable ({fallback_error})"
                ) from fallback_error
            enriched.raw_provider_fields["fundamentals_primary_error"] = str(primary_error)[:240]
            return enriched
