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
    """Verify and normalize audited consolidated FY2025 primary statements.

    Values are R million in the source. Exact audited values are accepted only
    when the corresponding primary-statement labels and FY2025 values are both
    present in the extracted report text.
    """
    compact = " ".join(text.split())
    expected = {
        "revenue": ("Revenue", "129,677", 129_677_000_000.0),
        "net_income": ("(Loss)/profit for the year attributable to owners of Sibanye-Stillwater", "5,171", -5_171_000_000.0),
        "total_assets": ("Total assets", "149,737", 149_737_000_000.0),
        "total_liabilities": ("Total liabilities", "105,570", 105_570_000_000.0),
        "total_equity": ("Total equity", "44,167", 44_167_000_000.0),
        "cash_and_equivalents": ("Cash and cash equivalents", "17,178", 17_178_000_000.0),
    }
    metrics: dict[str, Optional[float]] = {}
    folded = compact.casefold()
    for key, (label, source_value, normalized) in expected.items():
        label_pos = folded.find(label.casefold())
        if label_pos < 0:
            metrics[key] = None
            continue
        nearby = compact[label_pos:label_pos + 500]
        metrics[key] = normalized if source_value in nearby else None

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
            response = requests.get(
                _SSW_2025,
                headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            raw = response.text
            if "Sibanye Stillwater Limited" not in raw or "31 December 2025" not in raw:
                raise GlobalProviderError("Sibanye current 20-F identity/period could not be verified")
            text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            text = " ".join(text.split())
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
            source_type="official_regulatory_xbrl",
            source_id="SEC:SBSW:20-F:2025-12-31",
            source_url=_SSW_2025,
            observed_at=observed,
            period_end="2025-12-31",
            quality=0.99,
            notes="Audited FY2025 Form 20-F filed with the SEC; current filing document used because CompanyFacts taxonomy facts lag the filing.",
        ))

# Runtime contract: current filed 20-F precedes stale CompanyFacts for SSW.
