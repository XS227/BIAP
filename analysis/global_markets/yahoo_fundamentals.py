"""Conservative public vendor fundamentals fallback for BIAP Global.

This adapter is intentionally *supplementary*. It fills financial-statement
fields for markets where the official filing adapter is unavailable or cannot
resolve an issuer, but its provenance is labelled as public vendor metrics and
therefore does not satisfy the Evidence Agent's official/verified fundamental
source requirement. Missing or ambiguous data remains missing.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .regional_yahoo_chart import RegionalYahooChartMarketProvider
from .source_cache import data_root, read_json, write_json_atomic

_BASE = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries"

_TYPES = (
    "annualTotalRevenue",
    "annualGrossProfit",
    "annualOperatingIncome",
    "annualNetIncome",
    "annualTotalAssets",
    "annualTotalLiabilitiesNetMinorityInterest",
    "annualStockholdersEquity",
    "annualCurrentAssets",
    "annualCurrentLiabilities",
    "annualCashCashEquivalentsAndShortTermInvestments",
    "annualOperatingCashFlow",
    "annualFreeCashFlow",
    "annualTotalDebt",
    "annualEBITDA",
    "annualBasicEPS",
)


class YahooFundamentalsProvider(FundamentalsProvider):
    """Read annual public financial metrics from Yahoo's timeseries endpoint.

    Values are useful for display and agent context, but the appended source type
    deliberately avoids the Evidence Agent's official-filing tokens. A stock can
    therefore gain non-empty Fundamentals/Quality cards without being promoted
    to a BUY merely because this vendor fallback exists.
    """

    provider_id = "yahoo-public-fundamentals-global"

    def __init__(self, *, timeout: float = 15.0, cache_hours: float = 24.0) -> None:
        self.timeout = max(3.0, float(timeout))
        self.cache_seconds = max(0.0, float(cache_hours) * 3600.0)

    @staticmethod
    def supported(company: GlobalCompany) -> bool:
        return RegionalYahooChartMarketProvider.supported(company.country, company.exchange)

    @staticmethod
    def _symbol(company: GlobalCompany) -> str:
        if not YahooFundamentalsProvider.supported(company):
            raise GlobalProviderError(
                f"Yahoo public fundamentals fallback is not enabled for {company.country}/{company.exchange}"
            )
        return RegionalYahooChartMarketProvider._vendor_symbol(company)

    @staticmethod
    def _parse_time(value: object) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _cache_path(self, symbol: str) -> Path:
        digest = hashlib.sha256(symbol.upper().encode("utf-8")).hexdigest()
        return data_root() / "cache" / "yahoo-fundamentals" / f"{digest}.json"

    def _cached(self, symbol: str) -> Optional[dict]:
        payload = read_json(self._cache_path(symbol))
        if not isinstance(payload, dict) or not isinstance(payload.get("payload"), dict):
            return None
        return payload

    def _request(self, symbol: str) -> dict:
        now = datetime.now(timezone.utc)
        cached = self._cached(symbol)
        if cached:
            fetched = self._parse_time(cached.get("fetchedAt"))
            if fetched is not None and (now - fetched.astimezone(timezone.utc)).total_seconds() <= self.cache_seconds:
                return cached["payload"]

        period1 = int((now - timedelta(days=365 * 6 + 30)).timestamp())
        period2 = int((now + timedelta(days=2)).timestamp())
        params = {
            "symbol": symbol,
            "type": ",".join(_TYPES),
            "period1": period1,
            "period2": period2,
            "merge": "false",
            "corsDomain": "finance.yahoo.com",
            "lang": "en-US",
            "region": "US",
        }
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 BIAP-Global/1.0 public fundamentals",
                },
            ) as client:
                response = client.get(f"{_BASE}/{symbol}", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cached:
                return cached["payload"]
            raise GlobalProviderError(f"Yahoo fundamentals request failed: {type(exc).__name__}") from exc

        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected Yahoo fundamentals response")
        timeseries = payload.get("timeseries")
        if not isinstance(timeseries, dict):
            raise GlobalProviderError("Yahoo fundamentals response has no timeseries object")
        error = timeseries.get("error")
        if error:
            raise GlobalProviderError(f"Yahoo fundamentals provider error: {str(error)[:240]}")

        write_json_atomic(self._cache_path(symbol), {
            "source": "Yahoo Finance public fundamentals timeseries",
            "symbol": symbol,
            "fetchedAt": now.isoformat(),
            "payload": payload,
        })
        return payload

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if isinstance(value, dict):
            value = value.get("raw")
        if value in (None, "", "NaN"):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return None if result != result else result

    @classmethod
    def _entries(cls, payload: dict, key: str) -> list[dict]:
        timeseries = payload.get("timeseries") if isinstance(payload.get("timeseries"), dict) else {}
        results = timeseries.get("result")
        if not isinstance(results, list):
            return []
        rows: list[dict] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            values = result.get(key)
            if isinstance(values, list):
                rows.extend(item for item in values if isinstance(item, dict))
        rows.sort(key=lambda row: str(row.get("asOfDate") or row.get("date") or ""), reverse=True)
        return rows

    @classmethod
    def _latest(cls, payload: dict, key: str, *, index: int = 0) -> Optional[float]:
        rows = cls._entries(payload, key)
        if len(rows) <= index:
            return None
        row = rows[index]
        return cls._number(row.get("reportedValue") if "reportedValue" in row else row.get("value"))

    @classmethod
    def _latest_date(cls, payload: dict) -> Optional[str]:
        dates: list[str] = []
        for key in _TYPES:
            for row in cls._entries(payload, key)[:1]:
                text = str(row.get("asOfDate") or row.get("date") or "").strip()
                if text:
                    dates.append(text[:10])
        return max(dates) if dates else None

    @classmethod
    def _currency(cls, payload: dict) -> Optional[str]:
        for key in _TYPES:
            for row in cls._entries(payload, key)[:1]:
                currency = str(row.get("currencyCode") or "").strip().upper()
                if len(currency) == 3:
                    return currency
        return None

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        return None if current is None or previous in (None, 0) else (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(value: Optional[float], revenue: Optional[float]) -> Optional[float]:
        return None if value is None or revenue in (None, 0) else value / revenue * 100.0

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        symbol = self._symbol(company)
        payload = self._request(symbol)

        revenue = self._latest(payload, "annualTotalRevenue")
        revenue_prev = self._latest(payload, "annualTotalRevenue", index=1)
        net_income = self._latest(payload, "annualNetIncome")
        net_income_prev = self._latest(payload, "annualNetIncome", index=1)
        period_end = self._latest_date(payload)

        values = {
            "revenue": revenue,
            "gross_profit": self._latest(payload, "annualGrossProfit"),
            "operating_income": self._latest(payload, "annualOperatingIncome"),
            "net_income": net_income,
            "total_assets": self._latest(payload, "annualTotalAssets"),
            "total_liabilities": self._latest(payload, "annualTotalLiabilitiesNetMinorityInterest"),
            "total_equity": self._latest(payload, "annualStockholdersEquity"),
            "current_assets": self._latest(payload, "annualCurrentAssets"),
            "current_liabilities": self._latest(payload, "annualCurrentLiabilities"),
            "cash_and_equivalents": self._latest(payload, "annualCashCashEquivalentsAndShortTermInvestments"),
            "operating_cash_flow": self._latest(payload, "annualOperatingCashFlow"),
            "free_cash_flow": self._latest(payload, "annualFreeCashFlow"),
            "total_debt": self._latest(payload, "annualTotalDebt"),
            "ebitda": self._latest(payload, "annualEBITDA"),
            "eps": self._latest(payload, "annualBasicEPS"),
        }
        if not any(value is not None for value in values.values()):
            raise GlobalProviderError(f"Yahoo fundamentals returned no annual financial metrics for {symbol}")

        enriched = replace(
            company,
            reporting_currency=self._currency(payload) or company.reporting_currency,
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=values["gross_profit"],
            operating_income=values["operating_income"],
            ebitda=values["ebitda"],
            net_income=net_income,
            net_margin_pct=self._margin(net_income, revenue),
            net_margin_prev_pct=self._margin(net_income_prev, revenue_prev),
            total_assets=values["total_assets"],
            total_liabilities=values["total_liabilities"],
            total_equity=values["total_equity"],
            current_assets=values["current_assets"],
            current_liabilities=values["current_liabilities"],
            cash_and_equivalents=values["cash_and_equivalents"],
            operating_cash_flow=values["operating_cash_flow"],
            free_cash_flow=values["free_cash_flow"],
            total_debt=values["total_debt"],
            eps=values["eps"],
            raw_provider_fields={
                **company.raw_provider_fields,
                "yahoo_fundamentals_symbol": symbol,
                "yahoo_fundamentals_period_end": period_end,
                "yahoo_fundamentals_supplement_only": True,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="public_vendor_financial_metrics",
            source_id=symbol,
            source_url=f"https://finance.yahoo.com/quote/{symbol}/financials/",
            observed_at=datetime.now(timezone.utc).isoformat(),
            period_end=period_end,
            quality=0.72,
            notes=(
                "Supplementary public vendor metrics only; does not count as official filing evidence "
                "and cannot by itself clear the BIAP Evidence gate."
            ),
        ))
