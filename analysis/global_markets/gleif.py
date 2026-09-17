"""Conservative legal-entity resolution for BIAP Global.

GLEIF is used to resolve issuer names to a Legal Entity Identifier (LEI). The
resolver prefers an exact legal-name match. When a market catalog abbreviates a
legal form (for example ``plc`` versus ``public limited company``), it may use a
strict legal-form-normalized fallback, but only when that fallback resolves to
one unique active LEI. Ambiguous/fuzzy business-name matches are still rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
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


def _fold_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


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
)


def _name_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^A-Z0-9]+", value.upper()) if token]


def _legal_core_tokens(value: str) -> list[str]:
    tokens = _name_tokens(value)
    changed = True
    while tokens and changed:
        changed = False
        for suffix in _LEGAL_FORM_SUFFIXES:
            n = len(suffix)
            if len(tokens) >= n and tuple(tokens[-n:]) == suffix:
                del tokens[-n:]
                changed = True
                break
    return tokens


def _legal_core(value: str) -> str:
    return "".join(_legal_core_tokens(value))


def _legal_core_query(value: str) -> str:
    return " ".join(_legal_core_tokens(value))


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
        )

    @staticmethod
    def _usable(resolution: LEIResolution) -> bool:
        if resolution.entity_status == "INACTIVE":
            return False
        return resolution.registration_status not in {"RETIRED", "ANNULLED", "DUPLICATE"}

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

    def resolve_exact_legal_name(self, name: str) -> LEIResolution:
        wanted = name.strip()
        if len(wanted) < 2:
            raise GlobalProviderError("legal name is required for GLEIF resolution")

        # First preserve the original strict behavior: punctuation/case may vary,
        # but the legal name itself must be identical.
        folded = _fold_name(wanted)
        exact = [match for match in self._search(wanted, page_size=50) if _fold_name(match.legal_name) == folded]
        unique_exact = {match.lei: match for match in exact}
        if len(unique_exact) == 1:
            return next(iter(unique_exact.values()))
        if len(unique_exact) > 1:
            raise GlobalProviderError(
                f"GLEIF exact-name resolution for {wanted!r} is ambiguous ({len(unique_exact)} active matches)"
            )

        # Fallback only for legal-form spelling/abbreviation differences. The
        # business-name core must remain exactly equal after removing a trailing
        # recognized legal form, and one unique LEI must survive.
        core = _legal_core(wanted)
        query = _legal_core_query(wanted)
        if len(core) < 4 or not query:
            raise GlobalProviderError(f"GLEIF exact-name resolution for {wanted!r} is unavailable")

        relaxed = [match for match in self._search(query) if _legal_core(match.legal_name) == core]
        unique_relaxed = {match.lei: match for match in relaxed}
        if len(unique_relaxed) != 1:
            raise GlobalProviderError(
                f"GLEIF legal-form-normalized resolution for {wanted!r} is ambiguous/unavailable "
                f"({len(unique_relaxed)} active matches)"
            )
        return next(iter(unique_relaxed.values()))
