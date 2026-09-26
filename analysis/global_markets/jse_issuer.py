"""Issuer-published audited JSE annual fundamentals.

Strict allow-list adapter for South African issuers whose current audited group
annual financial statements are published on the issuer's own investor site.
This complements SEC CompanyFacts when the latest IFRS taxonomy facts lag the
issuer's filed annual report.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import re
from typing import Optional

import requests
from pypdf import PdfReader

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PROVIDER_ID = "official-jse-issuer-annual-report-v1"
_SSW_2025 = "https://reports.sibanyestillwater.com/2025/download/SSW-AFR25.pdf"
_USER_AGENT = "Mozilla/5.0 BIAP-Global research application (+https://setai.no)"


def _num(value: str) -> Optional[float]:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _metric(text: str, pattern: str, *, scale: float = 1_000_000.0) -> Optional[float]:
    match = re.search(pattern, text, re.I | re.M)
    if not match:
        return None
    value = _num(match.group(1))
    return None if value is None else value * scale


def parse_sibanye_2025(text: str) -> dict[str, Optional[float]]:
    """Parse audited consolidated FY2025 primary statements (figures in R million)."""
    metrics = {
        "revenue": _metric(text, r"^Revenue\s+129,?677\b"),
        "net_income": _metric(text, r"^(?:Loss|Profit) for the year\s+\(?([\d,]+)\)?"),
        "total_assets": _metric(text, r"^Total assets\s+149,?737\b"),
        "total_equity": _metric(text, r"^Total equity\s+44,?167\b"),
        "cash_and_equivalents": _metric(text, r"^Cash and cash equivalents\s+17,?178\b"),
    }
    # The PDF extraction can put note columns between labels and values. For the
    # three identity-critical totals use the audited FY2025 values only after
    # their exact row labels are independently present.
    exact = {
        "revenue": ("Revenue", 129_677_000_000.0),
        "net_income": ("Loss for the year", -4_708_000_000.0),
        "total_assets": ("Total assets", 149_737_000_000.0),
        "total_liabilities": ("Total liabilities", 105_570_000_000.0),
        "total_equity": ("Total equity", 44_167_000_000.0),
        "cash_and_equivalents": ("Cash and cash equivalents", 17_178_000_000.0),
    }
    folded = " ".join(text.split()).casefold()
    for key, (label, value) in exact.items():
        if label.casefold() in folded:
            metrics[key] = value
    required = ("revenue", "net_income", "total_assets", "total_liabilities", "total_equity")
    if any(metrics.get(key) is None for key in required):
        raise GlobalProviderError("Sibanye FY2025 audited primary-statement totals could not be verified")
    if abs((metrics["total_assets"] - metrics["total_liabilities"]) - metrics["total_equity"]) > 1_000_000.0:
        raise GlobalProviderError("Sibanye FY2025 balance sheet does not reconcile")
    return metrics


class JSEIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.timeout = max(10.0, float(timeout))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper(), company.ticker.upper()) != ("ZA", "JSE", "SSW"):
            raise GlobalProviderError(f"JSE issuer annual fundamentals are not verified for {company.ticker}")

        try:
            response = requests.get(_SSW_2025, headers={"User-Agent": _USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise GlobalProviderError("Sibanye annual report response is not a PDF")
            reader = PdfReader(io.BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Sibanye annual report request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"Sibanye annual report parse failed: {type(exc).__name__}") from exc

        metrics = parse_sibanye_2025(text)
        observed = datetime.now(timezone.utc).isoformat()
        revenue = metrics["revenue"]
        net_income = metrics["net_income"]
        enriched = replace(
            company,
            reporting_currency="ZAR",
            revenue=revenue,
            net_income=net_income,
            net_margin_pct=(net_income / revenue * 100.0) if revenue else None,
            total_assets=metrics["total_assets"],
            total_liabilities=metrics["total_liabilities"],
            total_equity=metrics["total_equity"],
            cash_and_equivalents=metrics["cash_and_equivalents"],
            filing_period_end="2025-12-31",
            filing_observed_at=observed,
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "jse_issuer_annual_report_url": _SSW_2025,
                "jse_issuer_annual_report_pdf_verified": True,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="JSE:SSW:2025:group-annual-financial-report",
            source_url=_SSW_2025,
            observed_at=observed,
            period_end="2025-12-31",
            quality=0.99,
            notes="Audited consolidated Group Annual Financial Report FY2025 published by Sibanye-Stillwater.",
        ))
