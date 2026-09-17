"""Conservative CVM issuer-name bridge for B3 reference catalog labels.

B3/reference vendors often shorten a legal issuer name to a trading/brand label
and append share-class markers (for example ``PETROBRAS PN``), while CVM DFP
uses the full legal denomination.  This resolver never uses edit-distance or
free-form fuzzy matching.  It accepts only exact normalized names, exact business
-token signatures, or exact token containment that resolves to one unique CNPJ.
"""
from __future__ import annotations

from typing import Any

from .cvm import CVMFundamentalsProvider, _business_signature, _name_tokens, _normalize_name
from .providers import GlobalProviderError


# Tokens that describe a B3 security/share class rather than the reporting legal
# entity. Keep this deliberately narrow. Unknown suffixes remain in the name and
# therefore cannot accidentally broaden an issuer match.
_SECURITY_TOKENS = {
    "on", "pn", "pna", "pnb", "pnc", "pnd",
    "unit", "units", "unt", "ordinaria", "ordinarias",
    "preferencial", "preferenciais", "preferred", "ordinary",
    "share", "shares", "shs", "npv", "class", "classe",
    "n1", "n2", "nm", "ma", "mb",
}
_LEGAL_TOKENS = {"s", "a", "sa", "ltda", "limitada"}


def _issuer_tokens(value: object) -> tuple[str, ...]:
    tokens = [
        token for token in _name_tokens(value)
        if token not in _LEGAL_TOKENS and token not in _SECURITY_TOKENS
    ]
    # Preserve uniqueness while discarding repeated display words.
    return tuple(dict.fromkeys(tokens))


def _unique_cnpjs(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("cnpj") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("cnpj") or "")
    }


class CVMResolvedFundamentalsProvider(CVMFundamentalsProvider):
    """CVM fundamentals provider with strict B3-label-to-CNPJ resolution."""

    provider_id = "cvm-open-data-dfp-resolved"

    @staticmethod
    def _resolve_rows(companies: dict[str, Any], company_name: str) -> tuple[list[dict[str, Any]], str]:
        # 1. Full normalized legal name.
        key = _normalize_name(company_name)
        exact = companies.get(key)
        if isinstance(exact, list) and exact:
            rows = [row for row in exact if isinstance(row, dict)]
            if len(_unique_cnpjs(rows)) == 1:
                return rows, "exact_legal_name"

        # 2. Same business tokens, merely reordered around punctuation/legal form.
        wanted_signature = _business_signature(company_name)
        if wanted_signature:
            matches: list[dict[str, Any]] = []
            for indexed_name, rows in companies.items():
                if not isinstance(rows, list):
                    continue
                if _business_signature(indexed_name) == wanted_signature:
                    matches.extend(row for row in rows if isinstance(row, dict))
            if len(_unique_cnpjs(matches)) == 1:
                return matches, "exact_business_token_signature"

        # 3. B3 often supplies only a brand plus a share-class marker. Remove a
        # narrowly-defined set of security/legal-form tokens and require exact
        # token containment. The accepted candidates must still collapse to one
        # unique CVM CNPJ, otherwise the match is rejected.
        wanted = set(_issuer_tokens(company_name))
        anchors = {token for token in wanted if len(token) >= 5}
        if not wanted or not anchors:
            raise GlobalProviderError(f"no strict CVM issuer match for {company_name!r}")

        contained: list[dict[str, Any]] = []
        for indexed_name, rows in companies.items():
            if not isinstance(rows, list):
                continue
            candidate = set(_issuer_tokens(indexed_name))
            if not candidate:
                continue
            shared = wanted & candidate
            if not any(token in shared for token in anchors):
                continue
            # No approximate spelling: one token set must be a literal subset of
            # the other. This covers "PETROBRAS PN" vs the CVM legal name while
            # rejecting unrelated issuers with only a partial fuzzy resemblance.
            if wanted.issubset(candidate) or candidate.issubset(wanted):
                contained.extend(row for row in rows if isinstance(row, dict))

        cnpjs = _unique_cnpjs(contained)
        if len(cnpjs) != 1:
            raise GlobalProviderError(
                f"CVM issuer-token containment for {company_name!r} is ambiguous/unavailable "
                f"({len(cnpjs)} CNPJs)"
            )
        return contained, "unique_business_token_containment"
