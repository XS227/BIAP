"""Verified issuer-filed NZX Limited annual fundamentals.

NZX's public company announcement pages expose structured announcement metadata
and cryptographically-described attachments. This adapter is intentionally
strict: it currently supports NZX Limited (ticker NZX) only, selects the latest
annual-report announcement from NZX itself, verifies the attached PDF, and
parses primary consolidated statements conservatively.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import html
import re
from typing import Optional
from urllib.parse import urljoin

import requests
from pypdf import PdfReader

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PROVIDER_ID = "official-nzx-issuer-annual-report-v1"
_COMPANY_PAGE = "https://new.nzx.com/companies/{ticker}/announcements"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_SUPPORTED = {"NZX"}


def _number(text: str) -> Optional[float]:
    value = str(text or "").strip().replace(",", "")
    if not value or value in {"-", "—"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()").strip()
    try:
        result = float(value)
    except ValueError:
        return None
    return -result if negative else result


def _metric(text: str, pattern: str, *, scale: float) -> Optional[float]:
    m = re.search(pattern, text, re.I | re.M)
    if not m:
        return None
    value = _number(m.group(1))
    return None if value is None else value * scale


def _block(text: str, starts: tuple[str, ...], *, length: int = 9000) -> str:
    lower = text.casefold()
    positions = [lower.find(x.casefold()) for x in starts]
    positions = [x for x in positions if x >= 0]
    if not positions:
        return ""
    pos = min(positions)
    return text[pos:pos + length]


def parse_nzx_limited_annual_report(text: str) -> dict[str, Optional[float]]:
    income = _block(text, ("Group Income Statement",))
    position = _block(text, ("Group Statement of Financial Position",))
    cashflow = _block(text, ("Group Statement of Cash Flows",))
    if not income or not position or not cashflow:
        raise GlobalProviderError("NZX annual report primary statements were not found")

    # NZX Limited's consolidated primary statements are presented in $000.
    scale = 1000.0
    result = {
        "revenue": _metric(income, r"^Operating revenue\s+(?:\S+\s+)?([\d,]+)\s+[\d,(]", scale=scale),
        "net_income": _metric(income, r"^Profit for the year\s+(?:\S+\s+)?([\d,]+)\s+[\d,(]", scale=scale),
        "total_assets": _metric(position, r"^Total assets\s+([\d,]+)\s+[\d,]+", scale=scale),
        "total_liabilities": _metric(position, r"^Total liabilities\s+([\d,]+)\s+[\d,]+", scale=scale),
        "total_equity": _metric(position, r"^Total equity attributable to shareholders\s+([\d,]+)\s+[\d,]+", scale=scale),
        "cash_and_equivalents": _metric(position, r"^Cash and cash equivalents\s+(?:\S+\s+)?([\d,]+)\s+[\d,]+", scale=scale),
        "operating_cash_flow": _metric(cashflow, r"^Net cash provided by operating activities\s+(?:\S+\s+)?([\d,]+)\s+[\d,]+", scale=scale),
        "eps": _metric(income, r"^Basic \(cents per share\)\s+(?:\S+\s+)?([\d.]+)\s+[\d.]+", scale=0.01),
    }
    if result["revenue"] is None or result["net_income"] is None:
        raise GlobalProviderError("NZX annual report revenue/profit could not be verified")
    return result


def _next_payload(html: str) -> dict:
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if not m:
        raise GlobalProviderError("NZX page has no __NEXT_DATA__ payload")
    try:
        value = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        raise GlobalProviderError("NZX __NEXT_DATA__ payload is invalid") from exc
    if not isinstance(value, dict):
        raise GlobalProviderError("NZX __NEXT_DATA__ payload is not an object")
    return value


class NZXIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 50.0) -> None:
        self.timeout = max(10.0, float(timeout))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("NZ", "NZX"):
            raise GlobalProviderError(f"NZX issuer fundamentals are not configured for {company.country}/{company.exchange}")
        ticker = company.ticker.strip().upper()
        if ticker not in _SUPPORTED:
            raise GlobalProviderError(f"NZX issuer fundamentals are not verified for {ticker}")

        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-NZ,en;q=0.9"}
        company_url = _COMPANY_PAGE.format(ticker=ticker)
        try:
            listing = requests.get(company_url, headers=headers, timeout=self.timeout)
            listing.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"NZX company announcements request failed: {type(exc).__name__}") from exc

        links = re.findall(r'href=["\']([^"\']*/announcements/\d+)["\']', listing.text, re.I)
        links = list(dict.fromkeys(urljoin(company_url, link) for link in links))
        annual: Optional[dict] = None
        annual_url = ""
        annual_date = ""
        for url in links[:12]:
            try:
                page = requests.get(url, headers=headers, timeout=self.timeout)
                page.raise_for_status()
                payload = _next_payload(page.text)
            except (requests.RequestException, GlobalProviderError):
                continue
            ann = (((payload.get("props") or {}).get("pageProps") or {}).get("announcement") or {})
            if not isinstance(ann, dict):
                continue
            summary = ann.get("summary") or {}
            details = ann.get("details") or {}
            if str(summary.get("companyCode") or "").strip().upper() != ticker:
                continue
            title = str(summary.get("title") or "").strip()
            kind = str(summary.get("type") or "").strip().upper()
            lower = title.casefold()
            if kind not in {"ANNREP", "FLLYR"}:
                continue
            if "annual report" not in lower and "full year" not in lower:
                continue
            attachments = details.get("attachments") or []
            report = next(
                (
                    item for item in attachments
                    if isinstance(item, dict)
                    and "annual report" in str(item.get("label") or "").casefold()
                    and str(item.get("fileURL") or "").startswith("https://api.nzx.com/")
                ),
                None,
            )
            if report is None:
                continue
            published = str(summary.get("publicationDate") or details.get("releaseDate") or "")
            if annual is None or published > annual_date:
                annual = {"announcement": ann, "attachment": report}
                annual_url = url
                annual_date = published

        if annual is None:
            raise GlobalProviderError(f"NZX has no verified annual-report announcement for {ticker}")

        report_url = str(annual["attachment"].get("fileURL") or "")
        try:
            pdf = requests.get(report_url, headers=headers, timeout=self.timeout)
            pdf.raise_for_status()
            if not pdf.content.startswith(b"%PDF"):
                raise GlobalProviderError("NZX annual-report attachment is not a PDF")
            reader = PdfReader(io.BytesIO(pdf.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except requests.RequestException as exc:
            raise GlobalProviderError(f"NZX annual-report PDF request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"NZX annual-report PDF parse failed: {type(exc).__name__}") from exc

        metrics = parse_nzx_limited_annual_report(text)
        title = str((annual["announcement"].get("summary") or {}).get("title") or "")
        years = [int(x) for x in re.findall(r"\b20\d{2}\b", title + " " + text[:15000])]
        year = max((y for y in years if y <= datetime.now(timezone.utc).year), default=None)
        if year is None:
            raise GlobalProviderError("NZX annual-report period year could not be verified")

        revenue = metrics["revenue"]
        net_income = metrics["net_income"]
        net_margin = (net_income / revenue * 100.0) if revenue and net_income is not None else None
        observed = datetime.now(timezone.utc).isoformat()
        enriched = replace(
            company,
            reporting_currency="NZD",
            revenue=revenue,
            net_income=net_income,
            net_margin_pct=net_margin,
            total_assets=metrics["total_assets"],
            total_liabilities=metrics["total_liabilities"],
            total_equity=metrics["total_equity"],
            cash_and_equivalents=metrics["cash_and_equivalents"],
            operating_cash_flow=metrics["operating_cash_flow"],
            eps=metrics["eps"],
            filing_period_end=f"{year}-12-31",
            filing_observed_at=observed,
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "nzx_announcement_url": annual_url,
                "nzx_annual_report_url": report_url,
                "nzx_annual_report_title": title,
                "nzx_annual_report_pdf_verified": True,
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_financial_statement",
                source_id=f"NZX:{ticker}:{year}:annual-report",
                source_url=report_url,
                observed_at=observed,
                period_end=f"{year}-12-31",
                quality=0.99,
                notes="Issuer-filed audited annual report published through the official NZX announcement service.",
            ),
        )
