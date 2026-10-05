"""Official issuer fundamentals for Singapore Exchange Limited (SGX:S68).

BIAP intentionally does not scrape the generic SGXNet disclosure surface here.
For the exchange operator itself (S68), the adapter consumes SGX Group's own
FY2026 financial-results PDF from the Investor Relations static-file host.

The parser is deliberately narrow and fail-closed:
* exact SG / SGX / S68 issuer identity;
* one hard-coded official investorrelations.sgx.com PDF;
* PDF magic validation before parsing;
* exact FY2026 headline labels and comparative figures;
* statutory NPAT is used, never the adjusted NPAT as net_income.
"""
from __future__ import annotations

from dataclasses import replace
import io
import re

import httpx

from .gleif import _legal_core
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


SGX_FY2026_RESULTS_URL = (
    "https://investorrelations.sgx.com/static-files/"
    "dcbd5905-9373-4dc9-80f5-8dbff6b8d584"
)


def _million(value: str) -> float:
    return float(value.replace(",", "").strip()) * 1_000_000.0


def _required(pattern: str, text: str, *, label: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        raise GlobalProviderError(f"SGX FY2026 results missing verified {label}")
    return match


def parse_sgx_fy2026_results(text: str) -> dict:
    normalized = " ".join(str(text or "").replace("\u00a0", " ").split())
    if "FY2026" not in normalized or "Operating revenue" not in normalized:
        raise GlobalProviderError("SGX FY2026 result markers are missing")

    revenue_match = _required(
        r"Operating revenue increased\s+\$?[0-9,.]+\s+million.*?"
        r"to\s+\$?([0-9,.]+)\s+million\s*\(\$?([0-9,.]+)\s+million\)",
        normalized,
        label="operating revenue",
    )
    ebitda_npat = _required(
        r"SGX recorded EBITDA of\s+\$?([0-9,.]+)\s+million\s*"
        r"\(\$?([0-9,.]+)\s+million\)\s+and NPAT of\s+"
        r"\$?([0-9,.]+)\s+million\s*\(\$?([0-9,.]+)\s+million\)",
        normalized,
        label="EBITDA and statutory NPAT",
    )
    eps_match = _required(
        r"EPS was\s+([0-9.]+)\s+cents\s*\(([0-9.]+)\s+cents\)",
        normalized,
        label="basic EPS",
    )

    revenue = _million(revenue_match.group(1))
    revenue_prev = _million(revenue_match.group(2))
    ebitda = _million(ebitda_npat.group(1))
    net_income = _million(ebitda_npat.group(3))
    net_income_prev = _million(ebitda_npat.group(4))

    return {
        "revenue": revenue,
        "revenue_prev": revenue_prev,
        "revenue_yoy_pct": ((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None,
        "ebitda": ebitda,
        "net_income": net_income,
        "net_margin_pct": (net_income / revenue) * 100.0 if revenue else None,
        "net_margin_prev_pct": (net_income_prev / revenue_prev) * 100.0 if revenue_prev else None,
        # The PDF reports cents; GlobalCompany.eps follows the issuer's
        # reporting currency per share, so convert cents to SGD.
        "eps": float(eps_match.group(1)) / 100.0,
    }


class SGXIssuerFundamentalsProvider(FundamentalsProvider):
    """Exact S68 issuer-owned fundamentals; unsupported SG tickers fail closed."""

    provider_id = "sgx-official-issuer-financial-information"

    def __init__(self, *, timeout: float = 25.0) -> None:
        self.timeout = max(5.0, float(timeout))

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

    def _get_text(self) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "Accept": "application/pdf,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            ) as client:
                response = client.get(SGX_FY2026_RESULTS_URL)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise GlobalProviderError(f"SGX issuer FY2026 PDF request failed: HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise GlobalProviderError(
                f"SGX issuer FY2026 PDF request failed: {type(exc).__name__}"
            ) from exc

        body = response.content
        if not body.startswith(b"%PDF-"):
            raise GlobalProviderError("SGX FY2026 result response is not a PDF")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(body))
            chunks = [(page.extract_text() or "") for page in reader.pages[:8]]
        except Exception as exc:
            raise GlobalProviderError(
                f"SGX FY2026 PDF text extraction failed: {type(exc).__name__}"
            ) from exc
        text = "\n".join(chunks)
        if len(text) < 500:
            raise GlobalProviderError("SGX FY2026 PDF extracted text is unexpectedly short")
        return text

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        self._verify_identity(company)
        metrics = parse_sgx_fy2026_results(self._get_text())

        enriched = replace(
            company,
            reporting_currency="SGD",
            filing_period_end="2026-06-30",
            filing_observed_at="2026-08-06T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "sgx_issuer_source": "fy2026_group_financial_results",
                "sgx_statutory_npat_used": True,
                "sgx_adjusted_npat_used": False,
            },
            **metrics,
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_issuer_fundamentals",
                source_id="S68:FY2026",
                source_url=SGX_FY2026_RESULTS_URL,
                observed_at="2026-08-06T00:00:00+00:00",
                period_end="2026-06-30",
                quality=0.96,
                notes=(
                    "SGX Group issuer-published FY2026 financial results; "
                    "statutory operating revenue, EBITDA, NPAT and EPS."
                ),
            ),
        )
