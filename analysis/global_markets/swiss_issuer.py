"""Verified Nestlé annual fundamentals for SIX Switzerland.

Switzerland has no single public machine-readable annual-statement feed covering
all SIX issuers. This adapter is intentionally narrow: it supports Nestlé S.A.
(NESN) only and reads the issuer-published consolidated annual financial
statements linked from Nestlé's official investor-relations Annual Report page.
Other Swiss issuers remain vendor-display-only until separately verified. PDF AES support is installed for issuer statements.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import re
from typing import Optional
from urllib.parse import urljoin

import requests
from pypdf import PdfReader

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PROVIDER_ID = "official-nestle-annual-financial-statements-v2"
_ANNUAL_PAGE = "https://www.nestle.com/investors/annual-report"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_SUPPORTED = {"NESN": "CH0038863350"}
# Nestlé's investor HTML can reject some server-side clients while its official
# static annual-report PDFs remain public. Keep the latest verified issuer URL
# as a deterministic primary source; page discovery may be re-enabled when a
# later annual report is published and verified.
_KNOWN_REPORTS = {
    2025: "https://www.nestle.com/sites/default/files/2026-02/corp-governance-compensation-financial-statements-2025-en.pdf",
}
_AMOUNT = r"\(?-?[0-9]{1,3}(?: [0-9]{3})?(?:\.[0-9]+)?\)?"


def _num(value: str, *, scale: float = 1.0) -> Optional[float]:
    text = str(value or "").strip().replace("\u00a0", " ").replace("'", "").replace(" ", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
    except ValueError:
        return None
    return (-number if negative else number) * scale


def _statement(text: str, header: str, required: tuple[str, ...], *, length: int = 14000) -> str:
    lower = text.casefold()
    needle = header.casefold()
    start = 0
    while True:
        pos = lower.find(needle, start)
        if pos < 0:
            break
        block = text[pos:pos + length]
        folded = block.casefold()
        if all(token.casefold() in folded for token in required):
            return block
        start = pos + len(needle)
    raise GlobalProviderError(f"Nestlé annual report statement not found: {header}")


def _pair(block: str, label_pattern: str, *, note: bool = True, scale: float = 1_000_000.0) -> tuple[Optional[float], Optional[float]]:
    optional_note = r"(?:\d+(?:/\d+)?\s+)?" if note else ""
    pattern = rf"^{label_pattern}\s+{optional_note}({_AMOUNT})\s+({_AMOUNT})(?:\s|$)"
    match = re.search(pattern, block, re.I | re.M)
    if not match:
        return None, None
    return _num(match.group(1), scale=scale), _num(match.group(2), scale=scale)


def parse_nestle_annual_financials(text: str) -> dict[str, Optional[float]]:
    income = _statement(
        text,
        "Consolidated income statement",
        ("Sales", "Profit for the year", "Basic earnings per share"),
    )
    balance = _statement(
        text,
        "Consolidated balance sheet",
        ("Total assets", "Total liabilities", "Total equity"),
    )
    cashflow = _statement(
        text,
        "Consolidated cash flow statement",
        ("Operating cash flow", "Capital expenditure"),
    )

    revenue, revenue_prev = _pair(income, r"Sales")
    net_income, net_income_prev = _pair(
        income,
        r"of which attributable to shareholders of the parent \(Net profit\)",
        note=False,
    )
    eps, eps_prev = _pair(income, r"Basic earnings per share", scale=1.0)
    current_assets, current_assets_prev = _pair(balance, r"Total current assets", note=False)
    total_assets, total_assets_prev = _pair(balance, r"Total assets", note=False)
    current_liabilities, current_liabilities_prev = _pair(balance, r"Total current liabilities", note=False)
    total_liabilities, total_liabilities_prev = _pair(balance, r"Total liabilities", note=False)
    total_equity, total_equity_prev = _pair(balance, r"Total equity", note=False)
    cash, cash_prev = _pair(balance, r"Cash and cash equivalents")
    operating_cash_flow, operating_cash_flow_prev = _pair(cashflow, r"Operating cash flow", note=False)
    capex, capex_prev = _pair(cashflow, r"Capital expenditure")
    debt_rows = re.findall(
        rf"^Financial debt\s+(?:\d+(?:/\d+)?\s+)?({_AMOUNT})\s+({_AMOUNT})(?:\s|$)",
        balance,
        re.I | re.M,
    )
    total_debt = sum((_num(row[0], scale=1_000_000.0) or 0.0) for row in debt_rows[:2]) or None
    total_debt_prev = sum((_num(row[1], scale=1_000_000.0) or 0.0) for row in debt_rows[:2]) or None

    if revenue is None or net_income is None or total_assets is None or total_liabilities is None:
        raise GlobalProviderError("Nestlé primary annual statement metrics could not be verified")

    revenue_yoy = (
        (revenue / revenue_prev - 1.0) * 100.0
        if revenue_prev not in (None, 0)
        else None
    )
    margin = (net_income / revenue * 100.0) if revenue else None
    margin_prev = (
        net_income_prev / revenue_prev * 100.0
        if net_income_prev is not None and revenue_prev not in (None, 0)
        else None
    )
    free_cash_flow = (
        operating_cash_flow - abs(capex)
        if operating_cash_flow is not None and capex is not None
        else None
    )
    free_cash_flow_prev = (
        operating_cash_flow_prev - abs(capex_prev)
        if operating_cash_flow_prev is not None and capex_prev is not None
        else None
    )

    return {
        "revenue": revenue,
        "revenue_prev": revenue_prev,
        "revenue_yoy_pct": revenue_yoy,
        "net_income": net_income,
        "net_income_prev": net_income_prev,
        "net_margin_pct": margin,
        "net_margin_prev_pct": margin_prev,
        "eps": eps,
        "eps_prev": eps_prev,
        "current_assets": current_assets,
        "current_assets_prev": current_assets_prev,
        "total_assets": total_assets,
        "total_assets_prev": total_assets_prev,
        "current_liabilities": current_liabilities,
        "current_liabilities_prev": current_liabilities_prev,
        "total_liabilities": total_liabilities,
        "total_liabilities_prev": total_liabilities_prev,
        "total_equity": total_equity,
        "total_equity_prev": total_equity_prev,
        "cash_and_equivalents": cash,
        "cash_and_equivalents_prev": cash_prev,
        "operating_cash_flow": operating_cash_flow,
        "operating_cash_flow_prev": operating_cash_flow_prev,
        "capital_expenditure": capex,
        "capital_expenditure_prev": capex_prev,
        "free_cash_flow": free_cash_flow,
        "free_cash_flow_prev": free_cash_flow_prev,
        "total_debt": total_debt,
        "total_debt_prev": total_debt_prev,
    }


class SwissIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.timeout = max(10.0, float(timeout))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("CH", "SIX"):
            raise GlobalProviderError(
                f"Swiss issuer fundamentals are not configured for {company.country}/{company.exchange}"
            )
        ticker = company.ticker.strip().upper()
        expected_isin = _SUPPORTED.get(ticker)
        if not expected_isin:
            raise GlobalProviderError(f"Swiss issuer fundamentals are not verified for {ticker}")
        if company.isin and company.isin.strip().upper() != expected_isin:
            raise GlobalProviderError(f"Nestlé identity mismatch for {ticker}: {company.isin}")

        headers = {
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": _ANNUAL_PAGE,
        }
        year = max(_KNOWN_REPORTS)
        if year > datetime.now(timezone.utc).year:
            raise GlobalProviderError("Nestlé annual Financial Statements year is in the future")
        pdf_url = _KNOWN_REPORTS[year]

        try:
            response = requests.get(pdf_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise GlobalProviderError("Nestlé annual Financial Statements resource is not a PDF")
            reader = PdfReader(io.BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Nestlé annual Financial Statements request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"Nestlé annual Financial Statements parse failed: {type(exc).__name__}") from exc

        if f"year ended December 31, {year}" not in text and f"December 31, {year}" not in text:
            raise GlobalProviderError("Nestlé annual Financial Statements period could not be verified")
        metrics = parse_nestle_annual_financials(text)
        observed = datetime.now(timezone.utc).isoformat()

        enriched = replace(
            company,
            reporting_currency="CHF",
            revenue=metrics["revenue"],
            revenue_prev=metrics["revenue_prev"],
            revenue_yoy_pct=metrics["revenue_yoy_pct"],
            net_income=metrics["net_income"],
            net_margin_pct=metrics["net_margin_pct"],
            net_margin_prev_pct=metrics["net_margin_prev_pct"],
            total_assets=metrics["total_assets"],
            total_liabilities=metrics["total_liabilities"],
            total_equity=metrics["total_equity"],
            current_assets=metrics["current_assets"],
            current_liabilities=metrics["current_liabilities"],
            cash_and_equivalents=metrics["cash_and_equivalents"],
            operating_cash_flow=metrics["operating_cash_flow"],
            free_cash_flow=metrics["free_cash_flow"],
            total_debt=metrics["total_debt"],
            eps=metrics["eps"],
            filing_period_end=f"{year}-12-31",
            filing_observed_at=observed,
            report_scope="consolidated IFRS",
            raw_provider_fields={
                **company.raw_provider_fields,
                "nestle_annual_report_page": _ANNUAL_PAGE,
                "nestle_financial_statements_url": pdf_url,
                "nestle_financial_statements_pdf_verified": True,
                "nestle_total_debt_prev": metrics["total_debt_prev"],
                "nestle_operating_cash_flow_prev": metrics["operating_cash_flow_prev"],
                "nestle_free_cash_flow_prev": metrics["free_cash_flow_prev"],
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_issuer_financial_statement",
                source_id=f"NESTLE:{ticker}:{year}:consolidated-financial-statements",
                source_url=pdf_url,
                observed_at=observed,
                period_end=f"{year}-12-31",
                quality=0.99,
                notes=(
                    "Nestlé S.A. issuer-published consolidated Financial Statements; "
                    "IFRS primary statements parsed conservatively."
                ),
            ),
        )
