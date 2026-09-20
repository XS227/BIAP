"""Official issuer financial statements for Hong Kong Exchanges and Clearing.

HKEX itself (HKEX:388 / 0388) publishes full consolidated annual financial
statements on the official HKEX Group Investor Relations site. BIAP uses that
issuer-owned PDF only for this exact issuer identity; this module is not a
generic HKEXnews crawler.

Controls:
* exact HK / HKEX ticker and issuer-name checks;
* one hard-coded official hkexgroup.com PDF;
* PDF magic/type validation and persistent raw-file cache;
* exact statement labels from the 2025 consolidated accounts;
* fail closed on any missing/changed label;
* source provenance is issuer-published official financial statements, not
  vendor fundamentals and not a claim of generic HKEXnews connectivity.
"""
from __future__ import annotations

from dataclasses import replace
import io
import re

import httpx

from .gleif import _legal_core
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import filing_path, sha256_bytes


HKEX_2025_FINANCIAL_STATEMENTS_URL = (
    "https://www.hkexgroup.com/-/media/HKEX-Group-Site/ssd/Investor-Relations/"
    "annouce/documents/2026/260226_accounts_e.pdf"
)
_CACHE_ID = "hkex-2025-annual-financial-statements"


def _number(value: str) -> float:
    text = value.replace(",", "").replace("$", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    return float(text)


_NUM = r"(?:\$?\(?[0-9][0-9,]*(?:\.[0-9]+)?\)?)"
_HKD_MILLION = 1_000_000.0


def _pair(text: str, label_pattern: str, *, label: str) -> tuple[float, float]:
    match = re.search(
        rf"{label_pattern}\s+({_NUM})\s+({_NUM})",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise GlobalProviderError(f"HKEX 2025 statements missing verified {label}")
    return _number(match.group(1)), _number(match.group(2))


def _position_row(text: str, label_pattern: str, *, label: str) -> tuple[float, float, float, float]:
    """Parse current/non-current/total for 2025 and 2024.

    Statement-of-financial-position rows are:
    current25, noncurrent25, total25, current24, noncurrent24, total24.
    A dash is represented as zero for rows such as cash; only the current and
    total values returned here are used.
    """
    token = rf"(?:{_NUM}|-)"
    match = re.search(
        rf"{label_pattern}\s+({token})\s+({token})\s+({token})\s+"
        rf"({token})\s+({token})\s+({token})",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise GlobalProviderError(f"HKEX 2025 statements missing verified {label}")

    def value(raw: str) -> float:
        return 0.0 if raw == "-" else _number(raw)

    return value(match.group(1)), value(match.group(3)), value(match.group(4)), value(match.group(6))


def parse_hkex_2025_statements(text: str) -> dict:
    normalized = " ".join(str(text or "").replace("\u2011", "-").replace("\u2013", "-").split())
    required = (
        "CONSOLIDATED INCOME STATEMENT",
        "FOR THE YEAR ENDED 31 DECEMBER 2025",
        "CONSOLIDATED STATEMENT OF FINANCIAL POSITION",
        "CONSOLIDATED STATEMENT OF CASH FLOWS",
    )
    if not all(marker in normalized.upper() for marker in required):
        raise GlobalProviderError("HKEX PDF is missing 2025 consolidated-statement markers")

    revenue, revenue_prev = _pair(normalized, r"(?<!Other )\bRevenue\b(?:\s+5)?", label="revenue")
    revenue *= _HKD_MILLION
    revenue_prev *= _HKD_MILLION

    ebitda, _ = _pair(
        normalized,
        r"EBITDA\s*\(non-HKFRS measure\)",
        label="EBITDA",
    )
    ebitda *= _HKD_MILLION

    operating_income, _ = _pair(normalized, r"Operating profit(?:\s+\d+)?", label="operating profit")
    operating_income *= _HKD_MILLION

    net_income, net_income_prev = _pair(
        normalized,
        r"Shareholders of HKEX(?:\s+\d+(?:\([a-z]\))?(?:\([ivx]+\))?)?",
        label="profit attributable to shareholders",
    )
    net_income *= _HKD_MILLION
    net_income_prev *= _HKD_MILLION

    # EPS is reported in HKD per share, not HKD millions.
    eps, _ = _pair(normalized, r"Basic earnings per share(?:\s+\d+\([a-z]\))?", label="basic EPS")

    current_assets, total_assets, _, total_assets_prev = _position_row(
        normalized, r"Total assets", label="total assets"
    )
    current_liabilities, total_liabilities, _, total_liabilities_prev = _position_row(
        normalized, r"Total liabilities", label="total liabilities"
    )
    total_equity, total_equity_prev = _pair(normalized, r"Total equity", label="total equity")
    cash_current, cash_total, _, _ = _position_row(
        normalized,
        r"Cash and cash equivalents(?:\s+\d+(?:,\d+)*)?",
        label="cash and cash equivalents",
    )
    _, debt_total, _, _ = _position_row(
        normalized, r"Borrowings(?:\s+\d+)?", label="borrowings"
    )
    current_assets *= _HKD_MILLION
    total_assets *= _HKD_MILLION
    total_assets_prev *= _HKD_MILLION
    current_liabilities *= _HKD_MILLION
    total_liabilities *= _HKD_MILLION
    total_liabilities_prev *= _HKD_MILLION
    total_equity *= _HKD_MILLION
    total_equity_prev *= _HKD_MILLION
    cash_current *= _HKD_MILLION
    cash_total *= _HKD_MILLION
    debt_total *= _HKD_MILLION

    operating_cash_flow, _ = _pair(
        normalized,
        r"Net cash inflow from operating activities",
        label="net cash inflow from operating activities",
    )
    operating_cash_flow *= _HKD_MILLION

    capex, _ = _pair(
        normalized,
        r"Payments for purchases of other fixed assets and intangible assets",
        label="capital expenditure",
    )
    capex *= _HKD_MILLION

    return {
        "revenue": revenue,
        "revenue_prev": revenue_prev,
        "revenue_yoy_pct": ((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None,
        "ebitda": ebitda,
        "operating_income": operating_income,
        "net_income": net_income,
        "net_margin_pct": (net_income / revenue) * 100.0 if revenue else None,
        "net_margin_prev_pct": (net_income_prev / revenue_prev) * 100.0 if revenue_prev else None,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "cash_and_equivalents": cash_total or cash_current,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": operating_cash_flow - abs(capex),
        "total_debt": debt_total,
        "eps": eps,
        "comparison": {
            "total_assets_prev": total_assets_prev,
            "total_liabilities_prev": total_liabilities_prev,
            "total_equity_prev": total_equity_prev,
        },
    }


class HKEXIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = "hkex-official-issuer-financial-statements"

    def __init__(self, *, timeout: float = 25.0) -> None:
        self.timeout = max(5.0, float(timeout))

    @staticmethod
    def _verify_identity(company: GlobalCompany) -> None:
        if company.country.strip().upper() != "HK":
            raise GlobalProviderError("HKEX issuer adapter only supports Hong Kong")
        ticker = company.ticker.strip().upper().lstrip("0")
        if ticker != "388":
            raise GlobalProviderError(
                f"no verified HK issuer parser for {company.ticker.strip().upper()}"
            )
        core = _legal_core(company.name)
        if core not in {
            "HONGKONGEXCHANGESANDCLEARING",
            "HONGKONGEXCHANGESCLEARING",
        }:
            raise GlobalProviderError(
                f"HKEX issuer identity mismatch for 388: {company.name!r}"
            )

    def _pdf_bytes(self) -> bytes:
        cache = filing_path("HK", _CACHE_ID, ".pdf")
        if cache.exists():
            body = cache.read_bytes()
            if body.startswith(b"%PDF-"):
                return body
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
                response = client.get(HKEX_2025_FINANCIAL_STATEMENTS_URL)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise GlobalProviderError(f"HKEX issuer PDF request failed: HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"HKEX issuer PDF request failed: {type(exc).__name__}") from exc

        body = response.content
        if not body.startswith(b"%PDF-"):
            raise GlobalProviderError("HKEX issuer financial-statement response is not a PDF")
        cache.parent.mkdir(parents=True, exist_ok=True)
        temp = cache.with_suffix(cache.suffix + ".tmp")
        temp.write_bytes(body)
        temp.replace(cache)
        return body

    @staticmethod
    def _pdf_text(body: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(body))
            # The headline statements occupy pages 1-7. Avoid processing the
            # entire annual document on every cold-cache parse.
            chunks = [(page.extract_text() or "") for page in reader.pages[:7]]
        except Exception as exc:
            raise GlobalProviderError(f"HKEX PDF text extraction failed: {type(exc).__name__}") from exc
        text = "\n".join(chunks)
        if len(text) < 1000:
            raise GlobalProviderError("HKEX PDF extracted text is unexpectedly short")
        return text

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        self._verify_identity(company)
        body = self._pdf_bytes()
        metrics = parse_hkex_2025_statements(self._pdf_text(body))
        comparison = metrics.pop("comparison")

        enriched = replace(
            company,
            reporting_currency="HKD",
            filing_period_end="2025-12-31",
            filing_observed_at="2026-02-26T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "hkex_issuer_source": "2025_consolidated_financial_statements",
                "hkex_pdf_sha256": sha256_bytes(body),
                **comparison,
            },
            **metrics,
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_issuer_financial_statement",
                source_id="HKEX:388:FY2025",
                source_url=HKEX_2025_FINANCIAL_STATEMENTS_URL,
                observed_at="2026-02-26T00:00:00+00:00",
                period_end="2025-12-31",
                quality=0.98,
                notes=(
                    "HKEX issuer-published consolidated financial statements for FY2025; "
                    "exact 388 issuer identity; raw official PDF cached with SHA-256."
                ),
            ),
        )
