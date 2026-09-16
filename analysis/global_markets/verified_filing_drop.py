"""Verified local filing-drop provider for BIAP Global.

Use this for markets where official disclosure access/redistribution is licensed
or issuer-report ingestion is handled by a separate authorized job. The provider
never parses arbitrary files: it accepts only normalized JSON records explicitly
marked verified and carrying source provenance.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import data_root, read_json

_ALLOWED_FIELDS = {
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow",
    "total_debt", "interest_expense", "eps", "audit_opinion",
}


class VerifiedFilingDropProvider(FundamentalsProvider):
    provider_id = "verified-filing-drop"

    def __init__(self, *, country: str, provider_names: tuple[str, ...]) -> None:
        self.country = country.strip().upper()
        self.provider_names = {name.strip().lower() for name in provider_names}

    def _path(self, company: GlobalCompany) -> Path:
        safe = "".join(ch for ch in company.ticker if ch.isalnum() or ch in {"-", "_", "."})
        return data_root() / "filings" / self.country / f"{safe}.json"

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != self.country:
            raise GlobalProviderError(f"filing drop is configured for {self.country}, not {company.country}")
        path = self._path(company)
        record = read_json(path)
        if not isinstance(record, dict):
            raise GlobalProviderError(f"no verified local filing record at {path}")
        if record.get("verified") is not True:
            raise GlobalProviderError(f"local filing record for {company.identity()} is not verified")
        provider = str(record.get("sourceProvider") or "").strip().lower()
        source_url = str(record.get("sourceUrl") or "").strip()
        period_end = str(record.get("periodEnd") or "").strip() or None
        observed_at = str(record.get("observedAt") or "").strip() or None
        if provider not in self.provider_names or not source_url or not period_end:
            raise GlobalProviderError("verified filing is missing an approved provider, source URL or period end")
        values = record.get("fundamentals")
        if not isinstance(values, dict):
            raise GlobalProviderError("verified filing has no normalized fundamentals")

        kwargs: dict[str, Any] = {}
        for key in _ALLOWED_FIELDS:
            if key not in values:
                continue
            kwargs[key] = values[key] if key == "audit_opinion" else self._number(values[key])
        kwargs.update({
            "reporting_currency": str(record.get("currency") or company.reporting_currency or company.currency),
            "filing_period_end": period_end,
            "filing_observed_at": observed_at,
            "report_scope": str(record.get("reportScope") or "consolidated"),
            "raw_provider_fields": {
                **company.raw_provider_fields,
                "verified_filing_path": str(path),
                "verified_filing_hash": record.get("sha256"),
            },
        })
        enriched = replace(company, **kwargs)
        return append_source(enriched, SourceEvidence(
            provider=provider,
            source_type="official_regulatory_filing",
            source_id=str(record.get("sourceId") or path.stem),
            source_url=source_url,
            observed_at=observed_at,
            period_end=period_end,
            quality=float(record.get("quality") or 0.95),
            notes="verified normalized filing stored in BIAP Global server evidence cache",
        ))
