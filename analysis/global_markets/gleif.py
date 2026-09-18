"""Conservative legal-entity resolution for BIAP Global.

GLEIF is used to resolve issuer names to a Legal Entity Identifier (LEI). The
resolver prefers an exact legal-name match. When a market catalog abbreviates a
legal form (for example ``plc`` versus ``public limited company``), it may use a
strict legal-form-normalized fallback, but only when that fallback resolves to
one unique active LEI. Ambiguous/fuzzy business-name matches are still rejected.

European catalog names frequently differ only by accents, punctuation or a
spelled-out legal form (``S.A.``, ``S.p.A.``, ``AB`` versus ``Aktiebolaget``).
Those differences are normalized conservatively. When several *exact* legal-name
records remain, issuer country may disambiguate by GLEIF legal jurisdiction; BIAP
never chooses an arbitrary fuzzy result.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Optional

import httpx

from .providers import GlobalProviderError


GLEIF_BASE = "https://api.gleif.org/api/v1"


@dataclass(frozen=True)
class LEIResolution:
    lei: str
    legal_name: str
    entity_status: Optional[str]
    registration_status: Optional[str]
    source_url: str
    legal_jurisdiction: Optional[str] = None


def _ascii(value: str) -> str:
    # NFKD keeps the business-name letters while discarding combining accents,
    # e.g. L'Oréal -> L'Oreal and Moët -> Moet. Do not transliterate arbitrary
    # words or use edit distance: business-name identity must remain exact.
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _fold_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _ascii(value).upper())


# Catalog vendors commonly abbreviate only the legal form while keeping the
# actual business name intact. These suffix groups are treated as equivalent for
# the fallback resolver. We never remove arbitrary business words.
_LEGAL_FORM_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("PUBLIC", "LIMITED", "COMPANY"),
    ("PUBLIC", "LIMITED"),
    ("LIMITED", "LIABILITY", "COMPANY"),
    ("LIMITED", "COMPANY"),
    ("JOINT", "STOCK", "COMPANY"),
    ("PLC",),
    ("LTD",),
    ("LIMITED",),
    ("INC",),
    ("INCORPORATED",),
    ("CORP",),
    ("CORPORATION",),
    ("CO",),
    ("COMPANY",),
    ("OYJ",),
    ("OY",),
    ("AB",),
    ("ASA",),
    ("AS",),
    ("AG",),
    ("SE",),
    ("SA",),
    ("SPA",),
    ("NV",),
    ("BV",),
    # Punctuated forms are tokenized one letter at a time.
    ("O", "Y", "J"),
    ("A", "B"),
    ("A", "S", "A"),
    ("A", "S"),
    ("S", "E"),
    ("S", "P", "A"),
    ("S", "A"),
    ("N", "V"),
    ("B", "V"),
)

# A few European legal forms are commonly written *before* the business name.
# They are legal-form words, not business-name words, and are stripped only from
# the beginning of the candidate name.
_LEGAL_FORM_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("AKTIEBOLAGET",),
)

# Market/reference catalogs often append a security/share-class description to
# the issuer legal name. These are listing descriptors, not issuer identity.
# Strip only recognized trailing descriptors; never remove arbitrary business
# words or use fuzzy edit-distance matching.
_DISPLAY_SECURITY_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("SERIES", "A", "SHARES"),
    ("SERIES", "B", "SHARES"),
    ("SERIES", "C", "SHARES"),
    ("CLASS", "A", "ORDINARY", "SHARES"),
    ("CLASS", "B", "ORDINARY", "SHARES"),
    ("CLASS", "A", "SHARES"),
    ("CLASS", "B", "SHARES"),
    ("ORDINARY", "SHARES"),
    ("REGISTERED", "SHARES"),
    ("COMMON", "STOCK"),
    ("COMMON", "SHARES"),
)


def _name_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^A-Z0-9]+", _ascii(value).upper()) if token]


def _legal_core_tokens(value: str) -> list[str]:
    tokens = _name_tokens(value)

    # Remove a trailing market security/share-class descriptor before legal-form
    # normalization. Example: "Aker ASA Series A Shares" -> "Aker ASA" -> "Aker".
    descriptor_changed = True
    while tokens and descriptor_changed:
        descriptor_changed = False
        for suffix in _DISPLAY_SECURITY_SUFFIXES:
            n = len(suffix)
            if len(tokens) >= n and tuple(tokens[-n:]) == suffix:
                del tokens[-n:]
                descriptor_changed = True
                break

    prefix_changed = True
    while tokens and prefix_changed:
        prefix_changed = False
        for prefix in _LEGAL_FORM_PREFIXES:
            n = len(prefix)
            if len(tokens) >= n and tuple(tokens[:n]) == prefix:
                del tokens[:n]
                prefix_changed = True
                break

    suffix_changed = True
    while tokens and suffix_changed:
        suffix_changed = False
        for suffix in _LEGAL_FORM_SUFFIXES:
            n = len(suffix)
            if len(tokens) >= n and tuple(tokens[-n:]) == suffix:
                del tokens[-n:]
                suffix_changed = True
                break
    return tokens


def _legal_core(value: str) -> str:
    return "".join(_legal_core_tokens(value))


def _legal_core_query(value: str) -> str:
    return " ".join(_legal_core_tokens(value))


def _jurisdiction_matches(country: Optional[str], jurisdiction: Optional[str]) -> bool:
    wanted = str(country or "").strip().upper()
    actual = str(jurisdiction or "").strip().upper()
    if not wanted or not actual:
        return False
    # GLEIF legalJurisdiction may be ISO-3166 country (ES) or subdivision
    # (US-DE). Only an exact country/prefix match is used for disambiguation.
    return actual == wanted or actual.startswith(wanted + "-")


class GLEIFResolver:
    provider_id = "gleif"

    def __init__(self, *, timeout: float = 12.0) -> None:
        self.timeout = max(3.0, float(timeout))

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{GLEIF_BASE}/{path.lstrip('/')}"
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"Accept": "application/vnd.api+json", "User-Agent": "BIAP-Global/1.0 entity-resolution"},
            ) as client:
                response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"GLEIF request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected GLEIF response")
        return payload

    @staticmethod
    def _resolution(row: dict) -> Optional[LEIResolution]:
        if not isinstance(row, dict):
            return None
        lei = str(row.get("id") or "").strip().upper()
        attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
        entity = attrs.get("entity") if isinstance(attrs.get("entity"), dict) else {}
        legal_name_obj = entity.get("legalName") if isinstance(entity.get("legalName"), dict) else {}
        legal_name = str(legal_name_obj.get("name") or "").strip()
        registration = attrs.get("registration") if isinstance(attrs.get("registration"), dict) else {}
        if len(lei) != 20 or not lei.isalnum() or not legal_name:
            return None
        return LEIResolution(
            lei=lei,
            legal_name=legal_name,
            entity_status=str(entity.get("status") or "").strip().upper() or None,
            registration_status=str(registration.get("status") or "").strip().upper() or None,
            source_url=f"{GLEIF_BASE}/lei-records/{lei}",
            legal_jurisdiction=str(entity.get("legalJurisdiction") or "").strip().upper() or None,
        )

    @staticmethod
    def _usable(resolution: LEIResolution) -> bool:
        if resolution.entity_status == "INACTIVE":
            return False
        return resolution.registration_status not in {"RETIRED", "ANNULLED", "DUPLICATE"}

    @staticmethod
    def _unique_or_country(
        matches: list[LEIResolution],
        *,
        country: Optional[str],
    ) -> tuple[Optional[LEIResolution], int]:
        unique = {match.lei: match for match in matches}
        if len(unique) == 1:
            return next(iter(unique.values())), 1
        if len(unique) > 1 and country:
            narrowed = {
                lei: match for lei, match in unique.items()
                if _jurisdiction_matches(country, match.legal_jurisdiction)
            }
            if len(narrowed) == 1:
                return next(iter(narrowed.values())), 1
        return None, len(unique)

    def verify_lei(self, lei: str) -> LEIResolution:
        wanted = lei.strip().upper()
        if len(wanted) != 20 or not wanted.isalnum():
            raise GlobalProviderError("invalid LEI format")
        payload = self._get(f"lei-records/{wanted}")
        row = payload.get("data")
        resolution = self._resolution(row) if isinstance(row, dict) else None
        if resolution is None or resolution.lei != wanted:
            raise GlobalProviderError(f"GLEIF could not verify LEI {wanted}")
        if not self._usable(resolution):
            raise GlobalProviderError(f"GLEIF entity for {wanted} is not active/usable")
        return resolution

    def _search(self, text: str, *, page_size: int = 100) -> list[LEIResolution]:
        payload = self._get(
            "lei-records",
            {
                "filter[entity.legalName]": text,
                "page[size]": max(1, min(int(page_size), 200)),
                "page[number]": 1,
            },
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise GlobalProviderError("GLEIF legal-name search returned no data list")
        result: list[LEIResolution] = []
        for row in rows:
            resolution = self._resolution(row)
            if resolution is not None and self._usable(resolution):
                result.append(resolution)
        return result

    def resolve_exact_legal_name(self, name: str, *, country: Optional[str] = None) -> LEIResolution:
        wanted = name.strip()
        if len(wanted) < 2:
            raise GlobalProviderError("legal name is required for GLEIF resolution")

        # First preserve strict behavior: punctuation, case and diacritics may
        # vary, but the legal-name letters themselves must be identical.
        folded = _fold_name(wanted)
        exact = [match for match in self._search(wanted, page_size=50) if _fold_name(match.legal_name) == folded]
        resolved, count = self._unique_or_country(exact, country=country)
        if resolved is not None:
            return resolved
        if count > 1:
            raise GlobalProviderError(
                f"GLEIF exact-name resolution for {wanted!r} is ambiguous ({count} active matches)"
            )

        # Fallback only for legal-form spelling/abbreviation differences. The
        # business-name core must remain exactly equal after removing recognized
        # prefix/suffix legal forms, and one unique LEI must survive (optionally
        # narrowed by the selected issuer jurisdiction).
        core = _legal_core(wanted)
        query = _legal_core_query(wanted)
        if len(core) < 4 or not query:
            raise GlobalProviderError(f"GLEIF exact-name resolution for {wanted!r} is unavailable")

        relaxed = [match for match in self._search(query) if _legal_core(match.legal_name) == core]
        resolved, count = self._unique_or_country(relaxed, country=country)
        if resolved is None:
            raise GlobalProviderError(
                f"GLEIF legal-form-normalized resolution for {wanted!r} is ambiguous/unavailable "
                f"({count} active matches)"
            )
        return resolved
