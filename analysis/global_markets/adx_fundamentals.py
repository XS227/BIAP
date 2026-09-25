"""Official ADX financial-summary fundamentals.

ADX's public issuer UI exposes a structured balance-sheet summary endpoint with
annual net profit, total equity, EPS and price/book. BIAP uses those values as
official exchange financial summary data, but deliberately does not label the
source as a complete financial statement: revenue, assets/liabilities and cash
flow are not present in this endpoint, so EvidenceAgent must remain blocked
until a complete verified filing source is connected.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
import re
from typing import Optional
from urllib.parse import urljoin

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PAGE_URL = "https://www.adx.ae/en/issuers/issuers-information/issuers-directory"
_SOURCE_URL = "https://apigateway.adx.ae/adx/listed-companies/1.1/balance-sheet/data"
_PROVIDER_ID = "official-adx-financial-summary"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_KEY_RE = re.compile(r'adx-Gateway-APIKey["\']?:["\']([^"\']+)', re.I)
_APP_RE = re.compile(r'<script[^>]+src=["\']([^"\']*/_next/static/chunks/pages/_app-[^"\']+\.js)["\']', re.I)


def _number(value: object) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
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


class ADXFinancialSummaryProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 35.0, years: int = 5) -> None:
        self.timeout = max(8.0, float(timeout))
        self.years = max(3, min(10, int(years)))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("AE", "ADX"):
            raise GlobalProviderError(f"ADX financial summary is not configured for {company.country}/{company.exchange}")
        symbol = company.ticker.strip().upper()
        if not symbol:
            raise GlobalProviderError("ADX financial summary requires a ticker")

        end_year = datetime.now(timezone.utc).year
        start_year = end_year - self.years + 1
        key = _public_gateway_key(min(25.0, self.timeout))
        try:
            response = requests.get(
                _SOURCE_URL,
                params={"symbol": symbol, "startYear": str(start_year), "endYear": str(end_year)},
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Channel-ID": "OSS WEB",
                    "Content-Type": "application/json",
                    "X-Correlation-ID": "biap-global-fundamentals",
                    "adx-Gateway-APIKey": key,
                    "Referer": _PAGE_URL,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"ADX financial summary request failed: {type(exc).__name__}") from exc

        latest, rows = parse_adx_financial_summary(payload)
        year = str(latest["financialYear"])
        enriched = replace(
            company,
            reporting_currency="AED",
            net_income=_number(latest.get("netProfit")),
            total_equity=_number(latest.get("totalEquity")),
            eps=_number(latest.get("earningsPerShare")),
            pb=_number(latest.get("priceToBookValue")),
            filing_period_end=f"{year}-12-31",
            filing_observed_at=datetime.now(timezone.utc).isoformat(),
            report_scope=company.report_scope or "ADX official annual financial summary",
            raw_provider_fields={
                **company.raw_provider_fields,
                "adx_financial_summary_latest": dict(latest),
                "adx_financial_summary_rows": rows,
                "adx_share_capital": _number(latest.get("shareCapital")),
                "adx_financial_summary_partial": True,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_exchange_financial_summary",
            source_id=f"ADX:{symbol}:{year}:annual-summary",
            source_url=_SOURCE_URL,
            observed_at=datetime.now(timezone.utc).isoformat(),
            period_end=f"{year}-12-31",
            quality=1.0,
            notes=(
                "Official ADX annual financial summary: net profit, total equity, EPS and P/B only. "
                "Not treated as complete filing evidence because revenue, assets/liabilities and cash flow are absent."
            ),
        ))
