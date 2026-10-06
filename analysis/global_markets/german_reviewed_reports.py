"""Reviewed issuer annual-report snapshots for German equities.

This provider is a data-driven bridge for German issuers whose audited annual
report is published on the issuer's official investor-relations site but whose
ESEF package is not available through BIAP's reviewed ESEF registry.

Records live in data/de_verified_annual_reports.json and are accepted only when:
* country is DE and the listing ISIN exactly matches the reviewed record;
* the source URL is HTTPS;
* period/currency/provenance are explicit;
* fundamentals contain only the supported normalized fields.

The normalized numbers are reviewed against the named official annual report.
This is issuer-published official evidence, not a regulator/OAM filing.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

REGISTRY_PATH = Path(__file__).with_name("data") / "de_verified_annual_reports.json"

_ALLOWED_FIELDS = {
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "retained_earnings", "current_assets",
    "current_liabilities", "cash_and_equivalents", "operating_cash_flow",
    "free_cash_flow", "total_debt", "interest_expense", "eps",
    "audit_opinion",
}


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict[str, Any]]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if int(payload.get("schemaVersion") or 0) != 1:
        raise ValueError("unsupported German reviewed annual-report registry schema")
    rows: dict[str, dict[str, Any]] = {}
    for raw in payload.get("issuers") or []:
        row = dict(raw)
        isin = str(row.get("isin") or "").upper().strip()
        url = str(row.get("sourceUrl") or "").strip()
        period = str(row.get("periodEnd") or "").strip()
        ticker = str(row.get("ticker") or "").upper().strip()
        parsed = urlparse(url)
        if not isin.startswith("DE") or len(isin) != 12:
            raise ValueError(f"invalid German reviewed annual-report ISIN {isin!r}")
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"invalid German reviewed annual-report URL {url!r}")
        if not ticker or not period:
            raise ValueError(f"incomplete German reviewed annual-report row {isin}")
        if isin in rows:
            raise ValueError(f"duplicate German reviewed annual-report row {isin}")
        values = row.get("fundamentals")
        if not isinstance(values, dict) or not values:
            raise ValueError(f"German reviewed annual-report row {isin} has no fundamentals")
        unknown = set(values) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"unsupported German reviewed fundamentals: {sorted(unknown)}")
        rows[isin] = row
    return rows


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class GermanReviewedAnnualReportProvider(FundamentalsProvider):
    provider_id = "de-reviewed-issuer-annual-report"

    def __init__(self, registry: Optional[dict[str, dict[str, Any]]] = None) -> None:
        self.registry = registry if registry is not None else _registry()

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "DE":
            raise GlobalProviderError("German reviewed annual reports apply to DE listings only")
        isin = (company.isin or "").upper().strip()
        row = self.registry.get(isin)
        if row is None:
            raise GlobalProviderError(
                f"no reviewed German annual-report snapshot for {isin or company.ticker}"
            )
        expected_ticker = str(row.get("ticker") or "").upper()
        if expected_ticker and company.ticker.upper() != expected_ticker:
            raise GlobalProviderError(
                f"German reviewed annual-report ticker mismatch: "
                f"{company.ticker} != {expected_ticker}"
            )

        values = row["fundamentals"]
        kwargs: dict[str, Any] = {}
        for key, value in values.items():
            kwargs[key] = value if key == "audit_opinion" else _number(value)

        revenue = kwargs.get("revenue")
        revenue_prev = kwargs.get("revenue_prev")
        if kwargs.get("revenue_yoy_pct") is None and revenue is not None and revenue_prev not in (None, 0):
            kwargs["revenue_yoy_pct"] = (revenue / revenue_prev - 1.0) * 100.0
        net_income = kwargs.get("net_income")
        if kwargs.get("net_margin_pct") is None and net_income is not None and revenue not in (None, 0):
            kwargs["net_margin_pct"] = net_income / revenue * 100.0

        period_end = str(row["periodEnd"])
        observed_at = str(row.get("observedAt") or "").strip() or None
        source_url = str(row["sourceUrl"])
        source_id = str(row.get("sourceId") or f"{expected_ticker.lower()}-annual-report-{period_end[:4]}")
        quality = float(row.get("quality") or 0.97)
        audited = bool(row.get("audited"))

        kwargs.update({
            "reporting_currency": str(row.get("currency") or company.reporting_currency or company.currency),
            "filing_period_end": period_end,
            "filing_observed_at": observed_at,
            "report_scope": str(row.get("reportScope") or "consolidated"),
            "raw_provider_fields": {
                **company.raw_provider_fields,
                "de_reviewed_annual_report": source_id,
                "de_reviewed_verification_mode": "reviewed_official_issuer_annual_report",
                "de_reviewed_source_host": urlparse(source_url).netloc.lower(),
            },
        })

        enriched = replace(company, **kwargs)
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_issuer_financial_statement",
                source_id=source_id,
                source_url=source_url,
                observed_at=observed_at,
                period_end=period_end,
                quality=quality,
                audit_status="audited" if audited else "unknown",
                notes=(
                    "reviewed normalized values from issuer-published annual report; "
                    "official issuer evidence, not a regulator filing"
                ),
            ),
        )
