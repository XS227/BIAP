"""Official SEC 10-K US-GAAP fallback for non-US cross-listed issuers.

Some Canadian issuers use Form 10-K rather than Form 40-F while their shares
also trade on TSX. This adapter reuses BIAP's cached SEC US-GAAP parser but
requires an exact legal-name identity match before the regulatory evidence is
accepted for a non-US listing.
"""
from __future__ import annotations

import threading
from dataclasses import replace
from datetime import date
from typing import Optional

from .cached_sec_edgar import CachedSECEdgarFundamentalsProvider
from .gleif import _legal_core
from .models import GlobalCompany
from .providers import GlobalProviderError
from .sec_identity import cik_by_name, identity_matches, issuer_names


_selected = threading.local()


class SECCrossListedUSGAAPFundamentalsProvider(CachedSECEdgarFundamentalsProvider):
    provider_id = "sec-edgar-crosslisted-10k-usgaap-cached"
    # Canadian MJDS filers (e.g. Canadian National) file US-GAAP statements on
    # Form 40-F rather than 10-K; both are audited annual SEC filings.
    ANNUAL_FORMS = {"10-K", "10-K/A", "40-F", "40-F/A"}

    @classmethod
    def _facts(cls, payload: dict) -> dict:
        """US-GAAP facts; furnished 6-K rows are kept only for filers that have
        no 10-K/40-F annual facts at all (otherwise older 6-K tags could win)."""
        gaap = super()._facts(payload)
        has_annual = any(
            row.get("form") in cls.ANNUAL_FORMS
            for concept in gaap.values() if isinstance(concept, dict)
            for entries in (concept.get("units") or {}).values() if isinstance(entries, list)
            for row in entries if isinstance(row, dict)
        )
        if not has_annual:
            return gaap
        return {
            name: {**concept, "units": {
                unit: [row for row in entries if not (isinstance(row, dict) and str(row.get("form", "")).startswith("6-K"))]
                for unit, entries in (concept.get("units") or {}).items() if isinstance(entries, list)
            }} if isinstance(concept, dict) else concept
            for name, concept in gaap.items()
        }

    @classmethod
    def _annual_series(cls, gaap: dict, tags: tuple[str, ...], count: int = 2) -> list[dict]:
        """Like the base parser, but across alternative tags take the series
        with the most recent period: an issuer that switched from 40-F to 10-K
        may have retired the first tag (Shopify 'Revenues' ends FY2023)."""
        best: list[dict] = []
        for tag in tags:
            series = super()._annual_series(gaap, (tag,), count)
            if series and (not best or str(series[0].get("end") or "") > str(best[0].get("end") or "")):
                best = series
        if best and not getattr(_selected, "form", None):
            _selected.form = str(best[0].get("form") or "")  # form of the first (revenue) series
        return best

    @classmethod
    def _annual_rows(cls, concept: dict) -> list[dict]:
        units = concept.get("units") if isinstance(concept, dict) else None
        if not isinstance(units, dict):
            return []
        def annual_6k(row: dict) -> bool:
            # Some MJDS filers (Canadian National) tag their year-end statements
            # only in the furnished 6-K. Accept those rows solely when SEC marks
            # them fiscal-year and a duration spans a full year.
            if row.get("form") not in {"6-K", "6-K/A"} or row.get("fp") != "FY":
                return False
            if not row.get("start"):
                return True  # balance-sheet instant at fiscal year end
            try:
                days = (date.fromisoformat(str(row["end"])) - date.fromisoformat(str(row["start"]))).days
            except (KeyError, ValueError):
                return False
            return 355 <= days <= 375

        rows = [
            row for entries in units.values() if isinstance(entries, list) for row in entries
            if isinstance(row, dict) and isinstance(row.get("val"), (int, float))
            and ((row.get("form") in cls.ANNUAL_FORMS and row.get("fp") in {None, "FY"}) or annual_6k(row))
        ]
        rows.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
        return rows

    @staticmethod
    def _identity_matches(company: GlobalCompany, entity_name: str) -> bool:
        selected = _legal_core(company.name)
        sec_name = _legal_core(entity_name)
        return bool(selected and sec_name and selected == sec_name)

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.strip().upper() == "US":
            raise GlobalProviderError("cross-listed SEC 10-K fallback is not used for US issuers")

        original_country = company.country
        names = issuer_names(company)

        def matches(entity: str) -> bool:
            return self._identity_matches(company, entity) or identity_matches(entity, names)

        # The inherited parser intentionally accepts US issuers only. A temporary
        # country proxy lets us reuse its strict standard US-GAAP 10-K extraction;
        # the selected exchange/ticker/MIC remain unchanged.
        _selected.form = None
        try:
            parsed = super().enrich_fundamentals(replace(company, country="US"))
            ticker_error: Optional[GlobalProviderError] = None
        except GlobalProviderError as exc:
            parsed, ticker_error = None, exc
        if parsed is None or not matches(parsed.name):
            # Local ticker missing from, or belonging to another filer in, the
            # SEC map: retry on the unique SEC filer whose title is this issuer.
            by_name = cik_by_name(self, names)
            if by_name is not None:
                proxy = replace(company, country="US", raw_provider_fields={**company.raw_provider_fields, "sec_cik": by_name})
                _selected.form = None
                try:
                    candidate = super().enrich_fundamentals(proxy)
                except GlobalProviderError:
                    candidate = None
                if candidate is not None and matches(candidate.name):
                    parsed = candidate
        if parsed is None:
            raise ticker_error or GlobalProviderError(f"SEC CIK not found for ticker {company.ticker}")
        if not matches(parsed.name):
            raise GlobalProviderError(
                f"SEC ticker identity does not match selected issuer {company.name!r}"
            )

        return replace(
            parsed,
            country=original_country,
            raw_provider_fields={
                **parsed.raw_provider_fields,
                "sec_form": (getattr(_selected, "form", None) or "10-K").split("/")[0],
                "sec_crosslisted_identity_verified": True,
            },
        )
