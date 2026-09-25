"""Official SEC 10-K US-GAAP fallback for non-US cross-listed issuers.

Some Canadian issuers use Form 10-K rather than Form 40-F while their shares
also trade on TSX. This adapter reuses BIAP's cached SEC US-GAAP parser but
requires an exact legal-name identity match before the regulatory evidence is
accepted for a non-US listing.
"""
from __future__ import annotations

from dataclasses import replace

from .cached_sec_edgar import CachedSECEdgarFundamentalsProvider
from .gleif import _legal_core
from .models import GlobalCompany
from .providers import GlobalProviderError


class SECCrossListedUSGAAPFundamentalsProvider(CachedSECEdgarFundamentalsProvider):
    provider_id = "sec-edgar-crosslisted-10k-usgaap-cached"

    @staticmethod
    def _identity_matches(company: GlobalCompany, entity_name: str) -> bool:
        selected = _legal_core(company.name)
        sec_name = _legal_core(entity_name)
        return bool(selected and sec_name and selected == sec_name)

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.strip().upper() == "US":
            raise GlobalProviderError("cross-listed SEC 10-K fallback is not used for US issuers")

        original_country = company.country
        # The inherited parser intentionally accepts US issuers only. A temporary
        # country proxy lets us reuse its strict standard US-GAAP 10-K extraction;
        # the selected exchange/ticker/MIC remain unchanged.
        parsed = super().enrich_fundamentals(replace(company, country="US"))
        if not self._identity_matches(company, parsed.name):
            raise GlobalProviderError(
                f"SEC ticker identity does not match selected issuer {company.name!r}"
            )

        return replace(
            parsed,
            country=original_country,
            raw_provider_fields={
                **parsed.raw_provider_fields,
                "sec_form": "10-K",
                "sec_crosslisted_identity_verified": True,
            },
        )
