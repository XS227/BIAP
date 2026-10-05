"""UK Companies House official metadata helper for BIAP Global.

UK listed-company financial analysis primarily uses UKSEF/ESEF structured
reports. Companies House is a corroborating official source for legal identity
and filing metadata and is cached separately; it is not misrepresented as a
market-price or parsed-fundamentals provider.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
import re
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source
from .source_cache import read_json, source_index_path, write_json_atomic

DEFAULT_BASE = "https://api.company-information.service.gov.uk"


def _normalize_name(value: str) -> str:
    text = value.casefold().replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [word for word in text.split() if word not in {"plc", "limited", "ltd"}]
    return " ".join(words)


class CompaniesHouseClient:
    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 12.0) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_COMPANIES_HOUSE_API_KEY") or "").strip()
        self.base = os.environ.get("BIAP_COMPANIES_HOUSE_BASE", DEFAULT_BASE).rstrip("/")
        self.timeout = max(3.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_COMPANIES_HOUSE_API_KEY is required")

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, auth=(self.api_key, ""), headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base}/{path.lstrip('/')}" , params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"Companies House request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected Companies House response")
        return payload

    def resolve_exact(self, legal_name: str) -> dict:
        wanted = _normalize_name(legal_name)
        if not wanted:
            raise GlobalProviderError("legal company name is required")
        payload = self._get("search/companies", {"q": legal_name, "items_per_page": 30})
        rows = payload.get("items")
        exact = [row for row in rows if isinstance(row, dict) and _normalize_name(str(row.get("title") or "")) == wanted] if isinstance(rows, list) else []
        numbers = {str(row.get("company_number") or "") for row in exact if row.get("company_number")}
        if len(numbers) != 1:
            raise GlobalProviderError(f"Companies House exact legal-name match is ambiguous ({len(numbers)} company numbers)")
        company_number = next(iter(numbers))
        profile = self._get(f"company/{company_number}")
        return {"companyNumber": company_number, "profile": profile}

    def filing_history(self, company_number: str, *, items_per_page: int = 100) -> dict:
        return self._get(f"company/{company_number}/filing-history", {"items_per_page": min(max(items_per_page, 1), 100)})


def cache_company(legal_name: str) -> dict:
    client = CompaniesHouseClient()
    resolved = client.resolve_exact(legal_name)
    number = resolved["companyNumber"]
    history = client.filing_history(number)
    path = source_index_path("companies-house")
    index = read_json(path, {"source": "UK Companies House API", "companies": {}})
    if not isinstance(index, dict):
        index = {"source": "UK Companies House API", "companies": {}}
    companies = index.get("companies") if isinstance(index.get("companies"), dict) else {}
    companies[number] = {
        "legalName": legal_name,
        "profile": resolved["profile"],
        "filingHistory": history,
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
    }
    index["companies"] = companies
    index["updatedAt"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(path, index)
    return {"companyNumber": number, "path": str(path)}


class CompaniesHouseCorroborator:
    """Append UK legal-entity/filing metadata without pretending it is XBRL data."""

    provider_id = "companies-house"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 12.0) -> None:
        self.client = CompaniesHouseClient(api_key=api_key, timeout=timeout)

    def corroborate(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "GB":
            raise GlobalProviderError(f"Companies House corroboration is for GB, not {company.country}")
        resolved = self.client.resolve_exact(company.name)
        number = resolved["companyNumber"]
        profile = resolved.get("profile") if isinstance(resolved.get("profile"), dict) else {}
        status = str(profile.get("company_status") or "").strip().lower() or None
        company_name = str(profile.get("company_name") or company.name).strip()
        updated = datetime.now(timezone.utc).isoformat()
        enriched = replace(
            company,
            raw_provider_fields={
                **company.raw_provider_fields,
                "companies_house_number": number,
                "companies_house_legal_name": company_name,
                "companies_house_status": status,
            },
        )
        if any(source.provider == self.provider_id and source.source_id == number for source in enriched.sources):
            return enriched
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_company_registry",
            source_id=number,
            source_url=f"https://find-and-update.company-information.service.gov.uk/company/{number}",
            observed_at=updated,
            quality=0.99,
            notes="Official UK legal-entity corroboration; not a substitute for UKSEF/ESEF financial statements.",
        ))
