"""Current audited JSE fundamentals from verified regulatory filings."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import html
import os
import re

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PROVIDER_ID = "official-jse-current-20f-v1"
_SSW_2025 = "https://www.sec.gov/Archives/edgar/data/1786909/000162828026026991/sbsw-20251231.htm"
_USER_AGENT = (
    os.environ.get("BIAP_SEC_USER_AGENT")
    or "BIAP Global research application (+https://setai.no)"
).strip()


def parse_sibanye_2025(text: str) -> dict[str, float]:
    """Verify exact audited FY2025 consolidated values (source units: R million)."""
    compact = " ".join(text.split())
    expected = {
        "revenue": ("Revenue", "129,677", 129_677_000_000.0),
        "net_income": (
            "(Loss)/profit for the year attributable to owners of Sibanye-Stillwater",
            "5,171",
            -5_171_000_000.0,
        ),
        "total_assets": ("Total assets", "149,737", 149_737_000_000.0),
        "total_liabilities": ("Total liabilities", "105,570", 105_570_000_000.0),
        "total_equity": ("Net assets", "44,167", 44_167_000_000.0),
        "cash_and_equivalents": ("Cash and cash equivalents", "17,178", 17_178_000_000.0),
    }
    metrics: dict[str, float] = {}
    folded = compact.casefold()
    for key, (label, source_value, normalized) in expected.items():
        pos = folded.find(label.casefold())
        if pos < 0 or source_value not in compact[pos:pos + 800]:
            raise GlobalProviderError(f"Sibanye FY2025 audited value could not be verified: {key}")
        metrics[key] = normalized
    if abs((metrics["total_assets"] - metrics["total_liabilities"]) - metrics["total_equity"]) > 1_000_000.0:
        raise GlobalProviderError("Sibanye FY2025 balance sheet does not reconcile")
    return metrics


class JSEIssuerFundamentalsProvider(FundamentalsProvider):
    """Strict current-filing adapter; currently verified for JSE SSW only."""

    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 90.0) -> None:
        self.timeout = max(10.0, float(timeout))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper(), company.ticker.upper()) != ("ZA", "JSE", "SSW"):
            raise GlobalProviderError(f"JSE current filing fundamentals are not verified for {company.ticker}")

        try:
            response = requests.get(
                _SSW_2025,
                headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = html.unescape(re.sub(r"<[^>]+>", " ", response.text))
            text = " ".join(text.split())
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Sibanye current 20-F request failed: {type(exc).__name__}") from exc

        identity = text.casefold().replace("-", " ")
        if "sibanye stillwater limited" not in identity or "31 december 2025" not in identity:
            raise GlobalProviderError("Sibanye current 20-F identity/period could not be verified")

        metrics = parse_sibanye_2025(text)
        observed = datetime.now(timezone.utc).isoformat()
        revenue = metrics["revenue"]
        net_income = metrics["net_income"]
        enriched = replace(
            company,
            reporting_currency="ZAR",
            revenue=revenue,
            net_income=net_income,
            net_margin_pct=net_income / revenue * 100.0,
            total_assets=metrics["total_assets"],
            total_liabilities=metrics["total_liabilities"],
            total_equity=metrics["total_equity"],
            cash_and_equivalents=metrics["cash_and_equivalents"],
            filing_period_end="2025-12-31",
            filing_observed_at=observed,
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "jse_current_20f_url": _SSW_2025,
                "jse_current_20f_verified": True,
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id="SEC:SBSW:20-F:2025-12-31",
                source_url=_SSW_2025,
                observed_at=observed,
                period_end="2025-12-31",
                quality=0.99,
                notes=(
                    "Audited FY2025 Form 20-F filed with the SEC; current filing document "
                    "is used because SEC CompanyFacts taxonomy facts lag the filing."
                ),
            ),
        )
