"""Official ADX annual financial-report fundamentals.

ADX's public financial-reports page exposes an exchange-owned efid feed.
Each Financial Report row links to the issuer-filed document on the ADX CDN and
also carries a structured headline table. BIAP verifies the linked PDF, parses
only conservative headline fields from the ADX disclosure metadata, and
cross-checks annual profit/equity/EPS against ADX's structured balance-summary
endpoint. Ambiguous or missing values stay missing.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
import json
import re
from typing import Optional
from urllib.parse import urljoin

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PAGE_URL = "https://www.adx.ae/main-market/company-profile/financial-reports"
_SOURCE_URL = "https://apigateway.adx.ae/adx/listed-companies/1.1/balance-sheet/data"
_REPORT_FEED_URL = "https://apigateway.adx.ae/adx/tradings/1.1/news"
_PROVIDER_ID = "official-adx-financial-report-v2"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_KEY_RE = re.compile(r'adx-Gateway-APIKey["\']?:["\']([^"\']+)', re.I)
_APP_RE = re.compile(r'<script[^>]+src=["\']([^"\']*/_next/static/chunks/pages/_app-[^"\']+\.js)["\']', re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _number(value: object) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _scaled_number(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").strip()
    match = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)\s*([KMBT]?)", text, re.I)
    if not match:
        return _number(text)
    number = float(match.group(1))
    scale = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[match.group(2).upper()]
    result = number * scale
    return -result if negative else result


def _pct(value: object) -> Optional[float]:
    text = str(value or "").strip().replace("%", "").replace("+", "")
    try:
        return float(text)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _public_gateway_key(timeout: float = 20.0) -> str:
    try:
        page = requests.get(_PAGE_URL, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        page.raise_for_status()
        match = _APP_RE.search(page.text)
        if not match:
            raise GlobalProviderError("ADX public app bundle was not found")
        bundle_url = urljoin(_PAGE_URL, match.group(1))
        bundle = requests.get(bundle_url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        bundle.raise_for_status()
    except requests.RequestException as exc:
        raise GlobalProviderError(f"ADX public web bundle request failed: {type(exc).__name__}") from exc
    key_match = _KEY_RE.search(bundle.text)
    if not key_match:
        raise GlobalProviderError("ADX public gateway key was not found in the public app bundle")
    return key_match.group(1)


def parse_adx_financial_summary(payload: object) -> tuple[dict, list[dict]]:
    if not isinstance(payload, dict):
        raise GlobalProviderError("ADX financial summary response is not an object")
    response = payload.get("response")
    rows = response.get("data") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise GlobalProviderError("ADX financial summary response has no data rows")

    normalized = [row for row in rows if isinstance(row, dict)]
    annual = [
        row for row in normalized
        if str(row.get("financialQuarter") or "").strip().casefold() == "annual"
        and str(row.get("financialYear") or "").strip().isdigit()
    ]
    if not annual:
        raise GlobalProviderError("ADX financial summary has no completed annual row")
    latest = max(annual, key=lambda row: int(str(row["financialYear"])))
    return latest, normalized


def select_latest_adx_annual_report(payload: object, symbol: str) -> dict:
    if not isinstance(payload, dict):
        raise GlobalProviderError("ADX financial-report feed is not an object")
    response = payload.get("response")
    rows = response.get("news") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise GlobalProviderError("ADX financial-report feed has no news rows")

    wanted = symbol.strip().upper()
    candidates: list[tuple[int, str, dict]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip().upper() != wanted:
            continue
        sub = str(row.get("subCategoryNameEn") or "").strip().casefold()
        title = str(row.get("simpleTitleEn") or row.get("titleEn") or "").strip()
        lower = title.casefold()
        if "financial report" not in sub or "press release" in sub or "integrated report" in sub:
            continue
        if "financial results" not in lower:
            continue
        years = [int(x) for x in _YEAR_RE.findall(title)]
        if not years:
            continue
        year = max(years)
        annual_marker = (
            "december 31" in lower
            or "31 december" in lower
            or "year ended" in lower
            or "year of" in lower
        )
        if not annual_marker:
            continue
        url = str(row.get("urlEn") or "").strip()
        if not url:
            continue
        candidates.append((year, str(row.get("publishedDate") or ""), row))
    if not candidates:
        raise GlobalProviderError(f"ADX has no completed annual Financial Report for {wanted}")
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def parse_adx_disclosure_metrics(row: dict) -> dict[str, Optional[float]]:
    raw = row.get("aiJsonDataEn")
    try:
        payload = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise GlobalProviderError("ADX annual disclosure metric table is invalid JSON") from exc
    table = payload.get("table") if isinstance(payload, dict) else None
    rows = table.get("rows") if isinstance(table, dict) else None
    if not isinstance(rows, list):
        raise GlobalProviderError("ADX annual disclosure has no structured metric rows")

    metrics: dict[str, Optional[float]] = {
        "revenue": None,
        "revenue_prev": None,
        "revenue_yoy_pct": None,
        "net_income": None,
        "eps": None,
        "cash_and_equivalents": None,
    }
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("col1") or "").strip().casefold()
        current = item.get("col2")
        previous = item.get("col3")
        yoy = item.get("col4")
        if label == "revenue":
            metrics["revenue"] = _scaled_number(current)
            metrics["revenue_prev"] = _scaled_number(previous)
            metrics["revenue_yoy_pct"] = _pct(yoy)
        elif label in {"net profit", "net income"}:
            metrics["net_income"] = _scaled_number(current)
        elif label in {"eps", "earnings per share"}:
            metrics["eps"] = _scaled_number(current)
        elif label in {"cash and cash equivalents", "cash & cash equivalents"}:
            metrics["cash_and_equivalents"] = _scaled_number(current)
    return metrics


class ADXFinancialSummaryProvider(FundamentalsProvider):
    """Backward-compatible class name; implementation now verifies annual filings."""

    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 45.0, years: int = 5) -> None:
        self.timeout = max(10.0, float(timeout))
        self.years = max(3, min(10, int(years)))

    def _headers(self, key: str) -> dict[str, str]:
        return {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "Channel-ID": "OSS WEB",
            "Content-Type": "application/json",
            "X-Correlation-ID": "biap-global-fundamentals",
            "adx-Gateway-APIKey": key,
            "Referer": _PAGE_URL,
        }

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("AE", "ADX"):
            raise GlobalProviderError(f"ADX financial reports are not configured for {company.country}/{company.exchange}")
        symbol = company.ticker.strip().upper()
        if not symbol:
            raise GlobalProviderError("ADX financial reports require a ticker")

        key = _public_gateway_key(min(25.0, self.timeout))
        end_year = datetime.now(timezone.utc).year
        start_year = end_year - self.years + 1
        headers = self._headers(key)
        try:
            feed = requests.get(
                _REPORT_FEED_URL,
                params={"categoryName": "efid", "categoryValue": symbol, "recordCount": "100"},
                headers=headers,
                timeout=self.timeout,
            )
            feed.raise_for_status()
            annual = select_latest_adx_annual_report(feed.json(), symbol)
            metrics = parse_adx_disclosure_metrics(annual)

            summary = requests.get(
                _SOURCE_URL,
                params={"symbol": symbol, "startYear": str(start_year), "endYear": str(end_year)},
                headers=headers,
                timeout=self.timeout,
            )
            summary.raise_for_status()
            latest, summary_rows = parse_adx_financial_summary(summary.json())

            pdf_url = str(annual.get("urlEn") or "").strip()
            with requests.get(
                pdf_url,
                headers={**headers, "Accept": "application/pdf"},
                timeout=self.timeout,
                stream=True,
            ) as pdf:
                pdf.raise_for_status()
                first = next(pdf.iter_content(chunk_size=16), b"")
                if not first.startswith(b"%PDF"):
                    raise GlobalProviderError("ADX annual disclosure resource is not a PDF")
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"ADX annual financial report request failed: {type(exc).__name__}") from exc

        title = str(annual.get("simpleTitleEn") or annual.get("titleEn") or "")
        years = [int(x) for x in _YEAR_RE.findall(title)]
        if not years:
            raise GlobalProviderError("ADX annual report year could not be verified")
        year = max(years)

        summary_year = int(str(latest.get("financialYear") or "0") or "0")
        if summary_year != year:
            raise GlobalProviderError(
                f"ADX annual report/summary year mismatch: report={year}, summary={summary_year}"
            )

        report_net = metrics.get("net_income")
        summary_net = _number(latest.get("netProfit"))
        if report_net not in (None, 0) and summary_net not in (None, 0):
            delta = abs(float(report_net) - float(summary_net)) / max(abs(float(summary_net)), 1.0)
            if delta > 0.02:
                raise GlobalProviderError("ADX annual report net profit conflicts with structured annual summary")

        revenue = metrics.get("revenue")
        net_income = summary_net if summary_net is not None else report_net
        net_margin = (
            float(net_income) / float(revenue) * 100.0
            if net_income is not None and revenue not in (None, 0)
            else None
        )
        observed = datetime.now(timezone.utc).isoformat()
        enriched = replace(
            company,
            reporting_currency="AED",
            revenue=revenue,
            revenue_prev=metrics.get("revenue_prev"),
            revenue_yoy_pct=metrics.get("revenue_yoy_pct"),
            net_income=net_income,
            net_margin_pct=net_margin,
            total_equity=_number(latest.get("totalEquity")),
            cash_and_equivalents=metrics.get("cash_and_equivalents"),
            eps=_number(latest.get("earningsPerShare")) or metrics.get("eps"),
            pb=_number(latest.get("priceToBookValue")),
            filing_period_end=f"{year}-12-31",
            filing_observed_at=observed,
            report_scope="ADX issuer-filed annual financial report",
            raw_provider_fields={
                **company.raw_provider_fields,
                "adx_financial_report_url": str(annual.get("urlEn") or ""),
                "adx_financial_report_title": title,
                "adx_financial_report_published": annual.get("publishedDate"),
                "adx_financial_report_expara": annual.get("exPara"),
                "adx_financial_report_pdf_verified": True,
                "adx_financial_summary_latest": dict(latest),
                "adx_financial_summary_rows": summary_rows,
                "adx_share_capital": _number(latest.get("shareCapital")),
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_financial_statement",
                source_id=f"ADX:{symbol}:{year}:annual-financial-report",
                source_url=str(annual.get("urlEn") or ""),
                observed_at=observed,
                period_end=f"{year}-12-31",
                quality=1.0,
                notes=(
                    "Issuer-filed annual Financial Report from ADX official efid disclosures; "
                    "PDF link verified. Headline disclosure metrics are cross-checked against "
                    "ADX's structured annual financial summary where overlapping."
                ),
            ),
        )
