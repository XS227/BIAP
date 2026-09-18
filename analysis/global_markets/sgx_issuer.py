"""Official issuer fundamentals for Singapore Exchange Limited (SGX:S68).

This is deliberately a narrow issuer-owned fallback, not an SGXNet scraper.
SGX's public company-announcements surface has access/redistribution constraints
and is therefore not promoted to a generic BIAP ingestion source here.

For S68, BIAP reads the issuer's own public Investor Relations financial-
information page and accepts only exact FY2026 key-figure labels. If that page
changes, the adapter fails closed and the Evidence Agent keeps the recommendation
blocked rather than guessing.

The page reports operating revenue, EBITDA and operating profit as SFRS(I)
key figures. It also reports an adjusted NPAT series; BIAP intentionally does
not map that adjusted value to net_income.
"""
from __future__ import annotations

from dataclasses import replace
from html import unescape
import re

import httpx

from .gleif import _legal_core
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


SGX_FINANCIAL_INFORMATION_URL = "https://investorrelations.sgx.com/financial-information"


def _plain_text(value: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", value or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(unescape(text).replace("\xa0", " ").split())


def _millions(value: str) -> float:
    return float(value.replace(",", "").strip()) * 1_000_000.0


def _row_values(text: str, label: str) -> tuple[float, float]:
    pattern = (
        rf"\b{re.escape(label)}\b\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)"
    )
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        raise GlobalProviderError(f"SGX issuer page missing verified {label!r} FY22-FY26 row")
    return _millions(match.group(5)), _millions(match.group(4))


class SGXIssuerFundamentalsProvider(FundamentalsProvider):
    """Exact S68 issuer-owned fundamentals; unsupported SG tickers fail closed."""

    provider_id = "sgx-official-issuer-financial-information"

    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = max(3.0, float(timeout))

    def _get_text(self) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": "BIAP-Global/1.0 issuer-financial-information",
                },
            ) as client:
                response = client.get(SGX_FINANCIAL_INFORMATION_URL)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise GlobalProviderError(f"SGX issuer request failed: HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"SGX issuer request failed: {type(exc).__name__}") from exc
        text = _plain_text(response.text)
        if len(text) < 200:
            raise GlobalProviderError("SGX issuer response is unexpectedly short")
        return text

    @staticmethod
    def _verify_identity(company: GlobalCompany) -> None:
        if company.country.strip().upper() != "SG":
            raise GlobalProviderError("SGX issuer adapter only supports Singapore")
        if company.ticker.strip().upper() != "S68":
            raise GlobalProviderError(f"no verified SG issuer parser for {company.ticker.strip().upper()}")
        if _legal_core(company.name) != "SINGAPOREEXCHANGE":
            raise GlobalProviderError(
                f"SGX issuer identity mismatch for S68: {company.name!r}"
            )

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        self._verify_identity(company)
        text = self._get_text()
        if not all(marker in text for marker in ("FY22", "FY23", "FY24", "FY25", "FY26")):
            raise GlobalProviderError("SGX issuer page does not expose the verified FY22-FY26 table")

        revenue, revenue_prev = _row_values(text, "Operating revenue")
        ebitda, _ = _row_values(text, "EBITDA")
        operating_income, _ = _row_values(text, "Operating profit")

        enriched = replace(
            company,
            reporting_currency="SGD",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None,
            ebitda=ebitda,
            operating_income=operating_income,
            filing_period_end="2026-06-30",
            filing_observed_at="2026-08-06T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "sgx_issuer_source": "financial_information_fy26",
                "sgx_adjusted_npat_intentionally_omitted": True,
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_issuer_fundamentals",
                source_id="S68:FY2026",
                source_url=SGX_FINANCIAL_INFORMATION_URL,
                observed_at="2026-08-06T00:00:00+00:00",
                period_end="2026-06-30",
                quality=0.94,
                notes=(
                    "Singapore Exchange Limited issuer-owned FY2026 key figures; "
                    "operating revenue, EBITDA and operating profit only. "
                    "Adjusted NPAT is intentionally not mapped to net_income."
                ),
            ),
        )
