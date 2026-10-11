"""Reviewed, SHA-256-pinned official annual-report snapshots.

Some listed issuers lodge an audited annual report with their regulator's
official filing system in a form BIAP cannot parse into standard facts:
* UK investment trusts and shells on the FCA National Storage Mechanism
  without inline XBRL (pdf2htmlEX conversions, RNS-only results);
* US registered closed-end funds on SEC EDGAR, whose Form N-CSR XBRL carries
  only the cef taxonomy (fees, leverage, NAV per share) and no financial
  statements, so SEC companyfacts returns 404 for them.

This module is the jurisdiction-neutral engine for those cases. Each
jurisdiction subclass supplies the registry file, the issuer key, the official
host/path rule for source URLs and the identity checks. Every registry row,
for every jurisdiction, must also:
* be pinned by the SHA-256 of the reviewed official document;
* name an ISO periodEnd, reporting currency and an explicit audit opinion that
  is not adverse or a disclaimer;
* carry only supported normalized fields, with
  total_assets - total_liabilities == total_equity when all three are present.

Providers built on this engine are fallbacks behind the tagged/XBRL chain: a
tagged filing for the same or a newer period always wins.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
from typing import Any, ClassVar, Optional

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

DATA_DIR = Path(__file__).with_name("data")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PERIOD = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ALLOWED_FIELDS = frozenset({
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "retained_earnings", "current_assets",
    "current_liabilities", "cash_and_equivalents", "operating_cash_flow",
    "free_cash_flow", "total_debt", "interest_expense", "eps",
    "audit_opinion",
})


def number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ReviewedAnnualReportProvider(FundamentalsProvider):
    """Base provider; subclasses define one jurisdiction's official source."""

    provider_id: ClassVar[str] = ""
    country: ClassVar[str] = ""
    registry_file: ClassVar[str] = ""
    # Prefix for error messages, e.g. "UK reviewed annual-report".
    label: ClassVar[str] = ""
    # Prefix for raw_provider_fields keys, e.g. "gb_reviewed".
    raw_prefix: ClassVar[str] = ""
    verification_mode: ClassVar[str] = ""
    default_source_id_prefix: ClassVar[str] = ""

    _loaded: ClassVar[dict[str, dict[str, dict[str, Any]]]] = {}

    def __init__(self, registry: Optional[dict[str, dict[str, Any]]] = None) -> None:
        self.registry = (
            {key: self.validate_row(row) for key, row in registry.items()}
            if registry is not None else self.load_registry()
        )

    # -- jurisdiction hooks -------------------------------------------------
    @classmethod
    def row_key(cls, row: dict) -> str:
        raise NotImplementedError

    @classmethod
    def company_key(cls, company: GlobalCompany) -> str:
        raise NotImplementedError

    @classmethod
    def validate_jurisdiction(cls, row: dict, key: str) -> None:
        """Normalize the row in place; raise ValueError on bad provenance."""
        raise NotImplementedError

    def check_identity(self, company: GlobalCompany, row: dict) -> None:
        """Raise GlobalProviderError when the listing is not the reviewed issuer."""

    def jurisdiction_fields(self, company: GlobalCompany, row: dict) -> dict[str, Any]:
        """Extra GlobalCompany fields (identifiers) set from the reviewed row."""
        return {}

    def raw_fields(self, row: dict) -> dict[str, Any]:
        return {}

    def notes(self, row: dict) -> str:
        raise NotImplementedError

    def wrong_country_message(self) -> str:
        return f"{self.label} snapshots apply to {self.country} listings only"

    def missing_message(self, company: GlobalCompany, key: str) -> str:
        return f"no {self.label} snapshot for {key or company.ticker}"

    # -- shared validation --------------------------------------------------
    @classmethod
    def validate_row(cls, raw: dict) -> dict:
        row = dict(raw)
        cls.validate_jurisdiction(row, cls.row_key(row))
        key = cls.row_key(row)
        period = str(row.get("periodEnd") or "").strip()
        if not _SHA256.match(str(row.get("sha256") or "")):
            raise ValueError(f"{cls.label} row {key} has no SHA-256 document pin")
        if not _PERIOD.match(period):
            raise ValueError(f"{cls.label} row {key} has invalid periodEnd {period!r}")
        if not str(row.get("currency") or "").strip():
            raise ValueError(f"{cls.label} row {key} has no reporting currency")
        values = row.get("fundamentals")
        if not isinstance(values, dict) or not values:
            raise ValueError(f"{cls.label} row {key} has no fundamentals")
        unknown = set(values) - ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"unsupported {cls.label} fundamentals: {sorted(unknown)}")
        opinion = str(values.get("audit_opinion") or "").strip().lower()
        if not opinion:
            raise ValueError(f"{cls.label} row {key} has no audit opinion")
        # An adverse opinion or disclaimer means the auditor does not stand behind
        # the numbers; they must not become recommendation-grade evidence.
        if "adverse" in opinion or "disclaimer" in opinion:
            raise ValueError(f"{cls.label} row {key} has an adverse/disclaimed audit opinion")
        assets = number(values.get("total_assets"))
        liabilities = number(values.get("total_liabilities"))
        equity = number(values.get("total_equity"))
        if None not in (assets, liabilities, equity):
            if abs(assets - liabilities - equity) > max(1.0, abs(assets) * 1e-6):
                raise ValueError(f"{cls.label} row {key} fails assets - liabilities = equity")
        return row

    @classmethod
    def load_registry(cls) -> dict[str, dict[str, Any]]:
        path = DATA_DIR / cls.registry_file
        cache_key = f"{cls.__module__}.{cls.__qualname__}:{path}"
        cached = ReviewedAnnualReportProvider._loaded.get(cache_key)
        if cached is not None:
            return cached
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("schemaVersion") or 0) != 1:
            raise ValueError(f"unsupported {cls.label} registry schema")
        rows: dict[str, dict[str, Any]] = {}
        for raw in payload.get("issuers") or []:
            row = cls.validate_row(raw)
            key = cls.row_key(row)
            if key in rows:
                raise ValueError(f"duplicate {cls.label} row {key}")
            rows[key] = row
        ReviewedAnnualReportProvider._loaded[cache_key] = rows
        return rows

    # -- enrichment ---------------------------------------------------------
    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != self.country:
            raise GlobalProviderError(self.wrong_country_message())
        key = self.company_key(company)
        row = self.registry.get(key)
        if row is None:
            raise GlobalProviderError(self.missing_message(company, key))
        self.check_identity(company, row)

        values = row["fundamentals"]
        kwargs: dict[str, Any] = {}
        for field, value in values.items():
            kwargs[field] = value if field == "audit_opinion" else number(value)

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
        source_id = str(row.get("sourceId") or f"{self.default_source_id_prefix}:{key}:{period_end}")
        quality = float(row.get("quality") or 0.97)

        row_raw = row.get("rawProviderFields")
        if not isinstance(row_raw, dict):
            row_raw = {}

        kwargs.update({
            "sector": company.sector or str(row.get("sector") or "").strip() or None,
            "industry": company.industry or str(row.get("industry") or "").strip() or None,
            "reporting_currency": str(row["currency"]),
            "filing_period_end": period_end,
            "filing_observed_at": observed_at,
            "report_scope": str(row.get("reportScope") or "company"),
            **self.jurisdiction_fields(company, row),
            "raw_provider_fields": {
                **company.raw_provider_fields,
                **row_raw,
                **self.raw_fields(row),
                f"{self.raw_prefix}_annual_report": source_id,
                f"{self.raw_prefix}_verification_mode": self.verification_mode,
                f"{self.raw_prefix}_document_sha256": row["sha256"],
            },
        })

        enriched = replace(company, **kwargs)
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_filing",
                source_id=source_id,
                source_url=source_url,
                observed_at=observed_at,
                period_end=period_end,
                quality=quality,
                audit_status="audited",
                notes=self.notes(row),
            ),
        )
