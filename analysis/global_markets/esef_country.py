"""Country-aware identity join for the ESEF fundamentals adapter.

The base ESEF parser remains intentionally source-format focused. This subclass
adds two conservative identity controls for market-catalog names:

1. GLEIF legal-name resolution receives the selected issuer country.
2. If several GLEIF records still have the *same normalized legal-name core*,
   BIAP asks the ESEF filing index which LEIs actually have a filing for that
   country. Exactly one matching-country filing may break the tie. Zero or more
   than one keeps the instrument blocked.

This is not fuzzy matching: BIAP never chooses a merely similar business name.
"""
from __future__ import annotations

from .esef import ESEFFundamentalsProvider, FILINGS_API
from .gleif import _legal_core, _legal_core_query
from .models import GlobalCompany
from .providers import GlobalProviderError


# Strict, country-scoped catalog-display aliases. These are not fuzzy matches:
# each key is an exact market-catalog issuer label verified against the issuer's
# legal name before being allowed into GLEIF/ESEF identity resolution.
_VERIFIED_LEGAL_NAME_ALIASES: dict[tuple[str, str], str] = {
    ("SE", "HENNES & MAURITZ AB"): "H & M Hennes & Mauritz AB",
}


class CountryAwareESEFFundamentalsProvider(ESEFFundamentalsProvider):
    provider_id = "esef-xbrl-country-aware"

    def _country_filing_exists(self, lei: str, country: str) -> bool:
        payload = self._get_json(FILINGS_API, params={
            "filter[entity.identifier]": lei,
            "page[size]": 10,
            "page[number]": 1,
            "sort": "-period_end",
        })
        rows = payload.get("data")
        if not isinstance(rows, list):
            return False
        wanted = country.strip().upper()
        for row in rows:
            if not isinstance(row, dict):
                continue
            attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            if str(attrs.get("country") or "").strip().upper() == wanted:
                return True
        return False

    def _resolve_by_country_filing(self, company: GlobalCompany):
        """Resolve an ambiguous exact legal core using ESEF-country evidence."""
        core = _legal_core(company.name)
        query = _legal_core_query(company.name)
        if len(core) < 4 or not query:
            return None

        candidates = {}
        # Some GLEIF searches work better with the market display name, while
        # others work better with the legal-form-stripped business-name core.
        for text in (company.name, query):
            try:
                rows = self.gleif._search(text, page_size=100)
            except GlobalProviderError:
                continue
            for row in rows:
                if _legal_core(row.legal_name) == core:
                    candidates[row.lei] = row

        if len(candidates) < 2:
            return None

        with_country_filing = []
        for row in candidates.values():
            try:
                if self._country_filing_exists(row.lei, company.country):
                    with_country_filing.append(row)
            except GlobalProviderError:
                # A source outage must not turn ambiguity into a guessed match.
                return None

        return with_country_filing[0] if len(with_country_filing) == 1 else None

    def _resolve_lei(self, company: GlobalCompany) -> tuple[str, str]:
        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name
        if not company.name or company.name == company.ticker:
            raise GlobalProviderError("ESEF requires a verified LEI or full legal company name")

        lookup_name = _VERIFIED_LEGAL_NAME_ALIASES.get(
            (company.country.strip().upper(), company.name.strip().upper()),
            company.name,
        )
        try:
            resolution = self.gleif.resolve_exact_legal_name(lookup_name, country=company.country)
            return resolution.lei, resolution.legal_name
        except GlobalProviderError as original:
            resolution = self._resolve_by_country_filing(company)
            if resolution is None:
                raise original
            return resolution.lei, resolution.legal_name
