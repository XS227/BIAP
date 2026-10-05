"""SEC EDGAR/XBRL fundamentals adapter for BIAP Global US instruments.

Uses SEC public ticker mapping and `data.sec.gov/api/xbrl/companyfacts`. No API
key is required, but responsible automated access must identify the caller via
`BIAP_SEC_USER_AGENT`. Only explicit standard US-GAAP facts are normalized;
missing or ambiguous values remain unavailable.
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
            raise GlobalProviderError("BIAP_SEC_USER_AGENT is required for responsible SEC automated access")

    def _get_json(self, url: str) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent, "Accept": "application/json"}) as client:
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
        cik = self._ticker_map().get(company.ticker.strip().upper())
        if cik is None:
            raise GlobalProviderError(f"SEC CIK not found for ticker {company.ticker.strip().upper()}")
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
                if not isinstance(row, dict) or row.get("form") not in {"10-K", "10-K/A"}:
                    continue
                if row.get("fp") not in {None, "FY"} or not isinstance(row.get("val"), (int, float)):
                    continue
                rows.append(row)
        rows.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
        return rows

    @classmethod
    def _annual_series(cls, gaap: dict, tags: tuple[str, ...], count: int = 2) -> list[dict]:
        # Issuers sometimes migrate between standard US-GAAP tags. Prefer the
        # candidate series whose newest annual fact is actually most recent;
        # tag order is only a tie-breaker, never a reason to select stale data.
        best: list[dict] = []
        best_key: tuple[str, str] = ("", "")
        for tag in tags:
            concept = gaap.get(tag)
            if not isinstance(concept, dict):
                continue
            unique: list[dict] = []
            seen_periods: set[str] = set()
            for row in cls._annual_rows(concept):
                period = str(row.get("end") or row.get("fy") or "")
                if not period or period in seen_periods:
                    continue
                seen_periods.add(period)
                unique.append(row)
                if len(unique) >= count:
                    break
            if unique:
                key = (
                    str(unique[0].get("end") or ""),
                    str(unique[0].get("filed") or ""),
                )
                if key > best_key:
                    best = unique
                    best_key = key
        return best

    @classmethod
    def _latest(cls, gaap: dict, tags: tuple[str, ...]) -> Optional[dict]:
        rows = cls._annual_series(gaap, tags, count=1)
        return rows[0] if rows else None

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

        revenues = self._annual_series(gaap, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"))
        net_income = self._annual_series(gaap, ("NetIncomeLoss", "ProfitLoss"))
        gross_profit = self._latest(gaap, ("GrossProfit",))
        operating_income = self._latest(gaap, ("OperatingIncomeLoss",))
        assets = self._latest(gaap, ("Assets",))
        liabilities = self._latest(gaap, ("Liabilities",))
        equity = self._latest(gaap, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
        current_assets = self._latest(gaap, ("AssetsCurrent",))
        current_liabilities = self._latest(gaap, ("LiabilitiesCurrent",))
        cash = self._latest(gaap, ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"))
        ocf = self._latest(gaap, ("NetCashProvidedByUsedInOperatingActivities",))
        capex = self._latest(gaap, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"))
        debt_current = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent"))
        debt_noncurrent = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtNoncurrent"))
        debt_total = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"))
        interest = self._latest(gaap, ("InterestExpenseNonOperating", "InterestExpenseDebt"))
        eps = self._latest(gaap, ("EarningsPerShareDiluted", "EarningsPerShareBasic"))
        dividend_per_share = self._latest(
            gaap,
            (
                "CommonStockDividendsPerShareDeclared",
                "CommonStockDividendsPerShareCashPaid",
            ),
        )
        # Only use a US-GAAP shares-count concept here. Do not substitute equity
        # or paid-in-capital dollar concepts, which would silently corrupt market cap.
        shares = self._latest(gaap, ("CommonStockSharesOutstanding",))

        # Anchor the normalized snapshot to one fiscal period. A company can
        # legitimately stop using a generic revenue concept (for example a
        # pre-revenue biotech) while its balance sheet, loss and cash flow keep
        # advancing. Never let one stale concept date the whole filing, and
        # never mix an older fact into a newer normalized statement.
        core_rows = [
            revenues[0] if revenues else None,
            net_income[0] if net_income else None,
            assets,
            liabilities,
            equity,
            current_assets,
            current_liabilities,
            cash,
            ocf,
            eps,
        ]
        period_end = max(
            (str(row.get("end") or "") for row in core_rows if row and row.get("end")),
            default="",
        ) or None

        def current_period_row(row: Optional[dict]) -> Optional[dict]:
            if row is None or period_end is None:
                return row
            return row if str(row.get("end") or "") == period_end else None

        def current_series_row(rows: list[dict]) -> Optional[dict]:
            if period_end is None:
                return rows[0] if rows else None
            return next(
                (row for row in rows if str(row.get("end") or "") == period_end),
                None,
            )

        def previous_series_row(rows: list[dict], current: Optional[dict]) -> Optional[dict]:
            if current is None:
                return None
            if period_end is None:
                return rows[1] if len(rows) > 1 else None
            return next(
                (
                    row for row in rows
                    if str(row.get("end") or "")
                    and str(row.get("end") or "") < period_end
                ),
                None,
            )

        revenue_row = current_series_row(revenues)
        revenue_prev_row = previous_series_row(revenues, revenue_row)
        income_row = current_series_row(net_income)
        income_prev_row = previous_series_row(net_income, income_row)

        gross_profit = current_period_row(gross_profit)
        operating_income = current_period_row(operating_income)
        assets = current_period_row(assets)
        liabilities = current_period_row(liabilities)
        equity = current_period_row(equity)
        current_assets = current_period_row(current_assets)
        current_liabilities = current_period_row(current_liabilities)
        cash = current_period_row(cash)
        ocf = current_period_row(ocf)
        capex = current_period_row(capex)
        debt_current = current_period_row(debt_current)
        debt_noncurrent = current_period_row(debt_noncurrent)
        debt_total = current_period_row(debt_total)
        interest = current_period_row(interest)
        eps = current_period_row(eps)
        dividend_per_share = current_period_row(dividend_per_share)

        revenue = self._value(revenue_row)
        revenue_prev = self._value(revenue_prev_row)
        income = self._value(income_row)
        income_prev = self._value(income_prev_row)
        ocf_value = self._value(ocf)
        capex_value = self._value(capex)
        fcf = None if ocf_value is None or capex_value is None else ocf_value - abs(capex_value)
        total_debt = self._value(debt_total)
        if total_debt is None:
            parts = [
                value
                for value in (self._value(debt_current), self._value(debt_noncurrent))
                if value is not None
            ]
            total_debt = sum(parts) if parts else None

        current_rows = [
            revenue_row,
            income_row,
            gross_profit,
            operating_income,
            assets,
            liabilities,
            equity,
            current_assets,
            current_liabilities,
            cash,
            ocf,
            capex,
            debt_current,
            debt_noncurrent,
            debt_total,
            interest,
            eps,
            dividend_per_share,
        ]
        filed_at = max(
            (str(row.get("filed") or "") for row in current_rows if row and row.get("filed")),
            default="",
        ) or None

        enriched = replace(
            company,
            name=str(payload.get("entityName") or company.name),
            reporting_currency=company.reporting_currency or "USD",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=self._value(gross_profit),
            operating_income=self._value(operating_income),
            net_income=income,
            net_margin_pct=self._margin(income, revenue),
            net_margin_prev_pct=self._margin(income_prev, revenue_prev),
            total_assets=self._value(assets),
            total_liabilities=self._value(liabilities),
            total_equity=self._value(equity),
            current_assets=self._value(current_assets),
            current_liabilities=self._value(current_liabilities),
            cash_and_equivalents=self._value(cash),
            operating_cash_flow=ocf_value,
            free_cash_flow=fcf,
            total_debt=total_debt,
            interest_expense=self._value(interest),
            eps=self._value(eps),
            dividend_per_share=self._value(dividend_per_share),
            shares_outstanding=company.shares_outstanding or self._value(shares),
            filing_period_end=period_end,
            filing_observed_at=filed_at,
            raw_provider_fields={**company.raw_provider_fields, "sec_cik": cik},
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id=f"CIK{padded}",
                source_url=source_url,
                observed_at=filed_at,
                period_end=period_end,
                quality=1.0,
                notes="standard US-GAAP facts from SEC companyfacts; annual 10-K/10-K-A preference",
            ),
        )
