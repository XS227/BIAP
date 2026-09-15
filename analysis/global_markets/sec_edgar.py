"""SEC EDGAR/XBRL fundamentals adapter for BIAP Global US instruments.

Uses the SEC's public ticker mapping and `data.sec.gov/api/xbrl/companyfacts`
endpoint. No SEC API key is required, but automated access must provide a
responsible User-Agent; configure `BIAP_SEC_USER_AGENT` (for example an app
name plus monitored contact address).

The parser is intentionally conservative: it reads only standard US-GAAP facts,
prefers filed 10-K/10-K-A fiscal-year facts, and leaves unsupported or ambiguous
values unavailable instead of inventing them.
"""

from __future__ import annotations

from dataclasses import replace
import os
import threading
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"

_ticker_lock = threading.Lock()
_ticker_cache: Optional[dict[str, int]] = None


class SECEdgarFundamentalsProvider(FundamentalsProvider):
    provider_id = "sec-edgar-xbrl"

    def __init__(self, *, user_agent: Optional[str] = None, timeout: float = 15.0) -> None:
        self.user_agent = (user_agent or os.environ.get("BIAP_SEC_USER_AGENT") or "").strip()
        self.timeout = max(3.0, float(timeout))
        if not self.user_agent:
            raise GlobalProviderError(
                "BIAP_SEC_USER_AGENT is required for responsible SEC automated access"
            )

    def _get_json(self, url: str) -> dict:
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            ) as client:
                response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"SEC request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected SEC JSON response")
        return payload

    def _ticker_map(self) -> dict[str, int]:
        global _ticker_cache
        if _ticker_cache is not None:
            return _ticker_cache
        with _ticker_lock:
            if _ticker_cache is not None:
                return _ticker_cache
            payload = self._get_json(SEC_TICKERS_URL)
            mapping: dict[str, int] = {}
            for row in payload.values():
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                try:
                    cik = int(row.get("cik_str"))
                except (TypeError, ValueError):
                    continue
                if ticker:
                    mapping[ticker] = cik
            if not mapping:
                raise GlobalProviderError("SEC ticker mapping returned no usable rows")
            _ticker_cache = mapping
            return mapping

    def _resolve_cik(self, company: GlobalCompany) -> int:
        explicit = company.raw_provider_fields.get("sec_cik")
        if explicit not in (None, ""):
            try:
                return int(explicit)
            except (TypeError, ValueError) as exc:
                raise GlobalProviderError(f"invalid SEC CIK for {company.identity()}") from exc
        ticker = company.ticker.strip().upper()
        cik = self._ticker_map().get(ticker)
        if cik is None:
            raise GlobalProviderError(f"SEC CIK not found for ticker {ticker}")
        return cik

    @staticmethod
    def _facts(payload: dict) -> dict:
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            return {}
        gaap = facts.get("us-gaap")
        return gaap if isinstance(gaap, dict) else {}

    @staticmethod
    def _annual_rows(concept: dict) -> list[dict]:
        units = concept.get("units") if isinstance(concept, dict) else None
        if not isinstance(units, dict):
            return []
        rows: list[dict] = []
        for entries in units.values():
            if not isinstance(entries, list):
                continue
            for row in entries:
                if not isinstance(row, dict):
                    continue
                if row.get("form") not in {"10-K", "10-K/A"}:
                    continue
                if row.get("fp") not in {None, "FY"}:
                    continue
                value = row.get("val")
                if not isinstance(value, (int, float)):
                    continue
                rows.append(row)
        rows.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
        return rows

    @classmethod
    def _annual_series(cls, gaap: dict, tags: tuple[str, ...], count: int = 2) -> list[dict]:
        for tag in tags:
            concept = gaap.get(tag)
            if not isinstance(concept, dict):
                continue
            rows = cls._annual_rows(concept)
            if not rows:
                continue
            unique: list[dict] = []
            seen_periods: set[str] = set()
            for row in rows:
                period = str(row.get("end") or row.get("fy") or "")
                if not period or period in seen_periods:
                    continue
                seen_periods.add(period)
                unique.append(row)
                if len(unique) >= count:
                    break
            if unique:
                return unique
        return []

    @staticmethod
    def _value(row: Optional[dict]) -> Optional[float]:
        if not row:
            return None
        value = row.get("val")
        return float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous in (None, 0):
            return None
        return (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(income: Optional[float], revenue: Optional[float]) -> Optional[float]:
        if income is None or revenue in (None, 0):
            return None
        return income / revenue * 100.0

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.strip().upper() != "US":
            raise GlobalProviderError("SEC EDGAR fundamentals adapter only supports US issuers")

        cik = self._resolve_cik(company)
        padded = f"{cik:010d}"
        source_url = f"{SEC_FACTS_BASE}/CIK{padded}.json"
        payload = self._get_json(source_url)
        gaap = self._facts(payload)
        if not gaap:
            raise GlobalProviderError(f"SEC returned no standard US-GAAP company facts for {company.identity()}")

        revenues = self._annual_series(
            gaap,
            (
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues",
                "SalesRevenueNet",
            ),
        )
        net_income = self._annual_series(gaap, ("NetIncomeLoss", "ProfitLoss"))
        assets = self._annual_series(gaap, ("Assets",), count=1)
        liabilities = self._annual_series(gaap, ("Liabilities",), count=1)
        equity = self._annual_series(
            gaap,
            ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            count=1,
        )
        ocf = self._annual_series(gaap, ("NetCashProvidedByUsedInOperatingActivities",), count=1)
        capex = self._annual_series(
            gaap,
            ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"),
            count=1,
        )

        revenue = self._value(revenues[0] if revenues else None)
        revenue_prev = self._value(revenues[1] if len(revenues) > 1 else None)
        income = self._value(net_income[0] if net_income else None)
        income_prev = self._value(net_income[1] if len(net_income) > 1 else None)
        ocf_value = self._value(ocf[0] if ocf else None)
        capex_value = self._value(capex[0] if capex else None)
        fcf = None if ocf_value is None or capex_value is None else ocf_value - abs(capex_value)
        period_end = None
        if revenues:
            period_end = str(revenues[0].get("end") or "") or None
        elif net_income:
            period_end = str(net_income[0].get("end") or "") or None

        enriched = replace(
            company,
            name=str(payload.get("entityName") or company.name),
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            net_income=income,
            net_margin_pct=self._margin(income, revenue),
            net_margin_prev_pct=self._margin(income_prev, revenue_prev),
            total_assets=self._value(assets[0] if assets else None),
            total_liabilities=self._value(liabilities[0] if liabilities else None),
            total_equity=self._value(equity[0] if equity else None),
            operating_cash_flow=ocf_value,
            free_cash_flow=fcf,
            filing_period_end=period_end,
            raw_provider_fields={**company.raw_provider_fields, "sec_cik": cik},
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id=f"CIK{padded}",
                source_url=source_url,
                period_end=period_end,
                quality=1.0,
                notes="standard US-GAAP facts from SEC companyfacts; annual 10-K/10-K-A preference",
            ),
        )
