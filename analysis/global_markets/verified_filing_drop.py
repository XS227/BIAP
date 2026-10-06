"""Verified local filing-drop provider for BIAP Global.

Use this for markets where official disclosure access/redistribution is licensed
or issuer-report ingestion is handled by a separate authorized job. The provider
never parses arbitrary files: it accepts only normalized JSON records explicitly
marked verified and carrying source provenance.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import data_root, read_json, source_index_path, write_json_atomic

_ALLOWED_SOURCE_TYPES = {
    "official_regulatory_filing",
    "official_regulatory_xbrl",
    "official_regulatory_financial_statement",
    "official_issuer_financial_statement",
    "official_issuer_fundamentals",
}

_ALLOWED_FIELDS = {
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "retained_earnings", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow",
    "total_debt", "interest_expense", "eps", "audit_opinion",
}


class VerifiedFilingDropProvider(FundamentalsProvider):
    provider_id = "verified-filing-drop"

    def __init__(
        self,
        *,
        country: str,
        provider_names: tuple[str, ...],
        enqueue_missing: bool = False,
        queue_name: Optional[str] = None,
    ) -> None:
        self.country = country.strip().upper()
        self.provider_names = {name.strip().lower() for name in provider_names}
        self.enqueue_missing = bool(enqueue_missing)
        self.queue_name = (
            str(queue_name or f"{self.country.lower()}-fundamentals-missing").strip()
        )

    def _enqueue(self, company: GlobalCompany) -> None:
        if not self.enqueue_missing:
            return
        path = source_index_path(self.queue_name)
        payload = read_json(path, default={})
        if not isinstance(payload, dict):
            payload = {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        identity = (company.isin or company.lei or company.ticker).strip().upper()
        if not identity:
            return
        previous = payload.get(identity) if isinstance(payload.get(identity), dict) else {}
        payload[identity] = {
            **previous,
            "country": company.country,
            "exchange": company.exchange,
            "ticker": company.ticker,
            "name": company.name,
            "isin": company.isin,
            "lei": company.lei,
            "reportingMarket": company.raw_provider_fields.get("reporting_market"),
            "marketSegment": company.raw_provider_fields.get("market_segment"),
            "firstSeenAt": previous.get("firstSeenAt") or now,
            "lastSeenAt": now,
            "requestCount": int(previous.get("requestCount") or 0) + 1,
            "priority": "interactive",
            "status": "pending",
        }
        write_json_atomic(path, payload)

    def _path(self, company: GlobalCompany) -> Path:
        safe = "".join(ch for ch in company.ticker if ch.isalnum() or ch in {"-", "_", "."})
        country_path = data_root() / "filings" / self.country / f"{safe}.json"
        if country_path.exists() or self.country not in {
            "AT", "BE", "DE", "DK", "ES", "FI", "FR", "GB", "IE", "IS",
            "IT", "NL", "NO", "PT", "SE",
        }:
            return country_path
        # Some deployments predate country-specific issuer drops and expose a
        # writable shared European evidence directory. The record is still
        # accepted only after provider/source/period verification below.
        return data_root() / "filings" / "EU" / f"{safe}.json"

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
            self._enqueue(company)
            raise GlobalProviderError(
                f"no verified local filing record at {path}; "
                f"official-source discovery queued"
            )
        if record.get("verified") is not True:
            raise GlobalProviderError(f"local filing record for {company.identity()} is not verified")
        provider = str(record.get("sourceProvider") or "").strip().lower()
        source_url = str(record.get("sourceUrl") or "").strip()
        period_end = str(record.get("periodEnd") or "").strip() or None
        observed_at = str(record.get("observedAt") or "").strip() or None
        if provider not in self.provider_names or not source_url or not period_end:
            raise GlobalProviderError("verified filing is missing an approved provider, source URL or period end")
        source_type = str(record.get("sourceType") or "official_regulatory_filing").strip().lower()
        if source_type not in _ALLOWED_SOURCE_TYPES:
            raise GlobalProviderError(f"verified filing has unsupported official source type {source_type!r}")
        values = record.get("fundamentals")
        if not isinstance(values, dict):
            raise GlobalProviderError("verified filing has no normalized fundamentals")

        kwargs: dict[str, Any] = {}
        for key in _ALLOWED_FIELDS:
            if key not in values:
                continue
            kwargs[key] = values[key] if key == "audit_opinion" else self._number(values[key])
        record_raw = record.get("rawProviderFields")
        if not isinstance(record_raw, dict):
            record_raw = {}
        kwargs.update({
            "sector": str(record.get("sector") or company.sector or "").strip() or None,
            "industry": str(record.get("industry") or company.industry or "").strip() or None,
            "reporting_currency": str(record.get("currency") or company.reporting_currency or company.currency),
            "filing_period_end": period_end,
            "filing_observed_at": observed_at,
            "report_scope": str(record.get("reportScope") or "consolidated"),
            "raw_provider_fields": {
                **company.raw_provider_fields,
                **record_raw,
                "verified_filing_path": str(path),
                "verified_filing_hash": record.get("sha256"),
                "verified_filing_verification_mode": record.get("verificationMode"),
            },
        })
        enriched = replace(company, **kwargs)
        return append_source(enriched, SourceEvidence(
            provider=provider,
            source_type=source_type,
            source_id=str(record.get("sourceId") or path.stem),
            source_url=source_url,
            observed_at=observed_at,
            period_end=period_end,
            quality=float(record.get("quality") or 0.95),
            notes="verified normalized filing stored in BIAP Global server evidence cache",
            provenance_status=str(record.get("provenanceStatus") or "independently_verified"),
            audit_status=str(record.get("auditStatus") or "unknown"),
        ))
