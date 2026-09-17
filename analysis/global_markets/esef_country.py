"""Country-aware identity join for the ESEF fundamentals adapter.

The base ESEF parser remains intentionally source-format focused. This small
subclass adds the issuer-country context needed to disambiguate otherwise exact
GLEIF legal-name collisions (for example multiple active Banco Santander S.A.
legal entities) without introducing fuzzy matching.
"""
from __future__ import annotations

from .esef import ESEFFundamentalsProvider
from .models import GlobalCompany
from .providers import GlobalProviderError


class CountryAwareESEFFundamentalsProvider(ESEFFundamentalsProvider):
    provider_id = "esef-xbrl-country-aware"

    def _resolve_lei(self, company: GlobalCompany) -> tuple[str, str]:
        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name
        if not company.name or company.name == company.ticker:
            raise GlobalProviderError("ESEF requires a verified LEI or full legal company name")
        resolution = self.gleif.resolve_exact_legal_name(company.name, country=company.country)
        return resolution.lei, resolution.legal_name
