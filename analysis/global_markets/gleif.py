"""Conservative legal-entity resolution for BIAP Global.

GLEIF is used only to resolve an exact legal name to a Legal Entity Identifier
(LEI). Ambiguous/fuzzy matches are rejected rather than guessed. This LEI then
becomes the join key into ESEF filings.
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
    # Deliberately punctuation/case-insensitive only. We do NOT strip corporate
    # suffixes or reorder tokens because that can collapse distinct legal entities.
    return re.sub(r"[^A-Z0-9]", "", value.upper())


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

    def verify_lei(self, lei: str) -> LEIResolution:
        wanted = lei.strip().upper()
        if len(wanted) != 20 or not wanted.isalnum():
            raise GlobalProviderError("invalid LEI format")
        payload = self._get(f"lei-records/{wanted}")
        row = payload.get("data")
        resolution = self._resolution(row) if isinstance(row, dict) else None
        if resolution is None or resolution.lei != wanted:
            raise GlobalProviderError(f"GLEIF could not verify LEI {wanted}")
        if resolution.entity_status == "INACTIVE":
            raise GlobalProviderError(f"GLEIF entity for {wanted} is inactive")
        return resolution

    def resolve_exact_legal_name(self, name: str) -> LEIResolution:
        wanted = name.strip()
        if len(wanted) < 2:
            raise GlobalProviderError("legal name is required for GLEIF resolution")
        payload = self._get(
            "lei-records",
            {
                "filter[entity.legalName]": wanted,
                "page[size]": 50,
                "page[number]": 1,
            },
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise GlobalProviderError("GLEIF legal-name search returned no data list")
        folded = _fold_name(wanted)
        matches: list[LEIResolution] = []
        for row in rows:
            resolution = self._resolution(row)
            if resolution is None:
                continue
            if resolution.entity_status == "INACTIVE":
                continue
            if _fold_name(resolution.legal_name) == folded:
                matches.append(resolution)
        unique = {match.lei: match for match in matches}
        if len(unique) != 1:
            raise GlobalProviderError(
                f"GLEIF exact-name resolution for {wanted!r} is ambiguous/unavailable ({len(unique)} exact active matches)"
            )
        return next(iter(unique.values()))
