"""South Korea OpenDART fundamentals adapter for BIAP Global.

Uses Financial Supervisory Service OpenDART corporation-code mapping and full
annual financial statements. Consolidated (CFS) statements are preferred and
separate (OFS) statements are fallback only. Account concepts are matched by
exact normalized XBRL account key/name so `Assets` cannot accidentally match
`CurrentAssets`, etc.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
import re
import threading
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

DEFAULT_BASE = "https://engopendart.fss.or.kr/engapi"
_corp_lock = threading.Lock()
_corp_cache: Optional[dict[str, str]] = None


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _account_key(value: Any) -> str:
    raw = str(value or "").strip()
    # Typical IDs are `ifrs-full_Revenue`; compare the local concept exactly.
    local = raw.rsplit("_", 1)[-1]
    return _normalized(local)


class OpenDARTFundamentalsProvider(FundamentalsProvider):
    provider_id = "opendart"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 15.0) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_OPENDART_API_KEY") or "").strip()
        self.base_url = os.environ.get("BIAP_OPENDART_BASE", DEFAULT_BASE).rstrip("/")
        self.timeout = max(3.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_OPENDART_API_KEY is required for OpenDART")

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/{endpoint.lstrip('/')}", params={"crtfc_key": self.api_key, **params})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"OpenDART request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected OpenDART response")
        status = str(payload.get("status") or "000")
        if status not in {"000", ""}:
            raise GlobalProviderError(f"OpenDART status {status}: {str(payload.get('message') or 'provider error')[:300]}")
        return payload

    def _corp_map(self) -> dict[str, str]:
        global _corp_cache
        if _corp_cache is not None:
            return _corp_cache
        with _corp_lock:
            if _corp_cache is not None:
                return _corp_cache
            rows = self._get("corpCode.json", {}).get("list")
            if not isinstance(rows, list):
                raise GlobalProviderError("OpenDART corporation-code response has no list")
            mapping = {
                str(row.get("stock_code") or "").strip(): str(row.get("corp_code") or "").strip()
                for row in rows if isinstance(row, dict) and row.get("stock_code") and row.get("corp_code")
            }
            if not mapping:
                raise GlobalProviderError("OpenDART returned no listed corporation-code mapping")
            _corp_cache = mapping
            return mapping

    def _corp_code(self, company: GlobalCompany) -> str:
        explicit = str(company.raw_provider_fields.get("opendart_corp_code") or "").strip()
        if explicit:
            return explicit
        corp = self._corp_map().get(company.ticker.strip())
        if corp is None:
            raise GlobalProviderError(f"OpenDART corporation code not found for {company.ticker.strip()}")
        return corp

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value in (None, "", "-"):
            return None
        text = str(value).replace(",", "").replace(" ", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _matches(row: dict, ids: tuple[str, ...], names: tuple[str, ...]) -> bool:
        account_key = _account_key(row.get("account_id"))
        name_key = _normalized(row.get("account_nm"))
        expected_ids = {_normalized(token) for token in ids}
        expected_names = {_normalized(token) for token in names}
        return account_key in expected_ids or (name_key and name_key in expected_names)

    @classmethod
    def _find(cls, rows: list[dict], ids: tuple[str, ...], names: tuple[str, ...] = ()) -> Optional[dict]:
        for row in rows:
            if cls._matches(row, ids, names):
                return row
        return None

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous in (None, 0):
            return None
        return (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(value: Optional[float], revenue: Optional[float]) -> Optional[float]:
        if value is None or revenue in (None, 0):
            return None
        return value / revenue * 100.0

    def _annual_rows(self, corp_code: str, year: int, fs_div: str) -> list[dict]:
        payload = self._get("fnlttSinglAcntAll.json", {
            "corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011", "fs_div": fs_div,
        })
        rows = payload.get("list")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _latest_statement(self, corp_code: str) -> tuple[list[dict], int, str]:
        raw_year = os.environ.get("BIAP_OPENDART_FISCAL_YEAR")
        try:
            start_year = int(raw_year) if raw_year else datetime.now(timezone.utc).year - 1
        except ValueError as exc:
            raise GlobalProviderError("BIAP_OPENDART_FISCAL_YEAR must be a year") from exc
        last_error: Optional[Exception] = None
        for year in range(start_year, start_year - 3, -1):
            for fs_div in ("CFS", "OFS"):
                try:
                    rows = self._annual_rows(corp_code, year, fs_div)
                except GlobalProviderError as exc:
                    last_error = exc
                    continue
                if rows:
                    return rows, year, fs_div
        if last_error:
            raise GlobalProviderError(f"no usable OpenDART annual statement: {last_error}")
        raise GlobalProviderError("no usable OpenDART annual statement found")

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "KR":
            raise GlobalProviderError("OpenDART adapter only supports South Korea")
        corp_code = self._corp_code(company)
        rows, year, fs_div = self._latest_statement(corp_code)

        revenue_row = self._find(rows, ("revenue",), ("Revenue", "Sales"))
        gross_row = self._find(rows, ("grossprofit",), ("Gross profit",))
        operating_row = self._find(rows, ("profitlossfromoperatingactivities", "operatingprofitloss", "operatingprofit"), ("Operating profit", "Operating income"))
        net_row = self._find(rows, ("profitloss",), ("Profit (loss)", "Net income"))
        assets_row = self._find(rows, ("assets",), ("Total assets",))
        liabilities_row = self._find(rows, ("liabilities",), ("Total liabilities",))
        equity_row = self._find(rows, ("equity",), ("Total equity",))
        current_assets_row = self._find(rows, ("currentassets",), ("Current assets",))
        current_liabilities_row = self._find(rows, ("currentliabilities",), ("Current liabilities",))
        cash_row = self._find(rows, ("cashandcashequivalents",), ("Cash and cash equivalents",))
        ocf_row = self._find(rows, ("cashflowsfromusedinoperatingactivities",), ("Cash flows from operating activities",))

        revenue = self._number(revenue_row.get("thstrm_amount")) if revenue_row else None
        revenue_prev = self._number(revenue_row.get("frmtrm_amount")) if revenue_row else None
        net_income = self._number(net_row.get("thstrm_amount")) if net_row else None
        net_income_prev = self._number(net_row.get("frmtrm_amount")) if net_row else None
        filing_no = str(rows[0].get("rcept_no") or "").strip() if rows else ""
        currency = str(rows[0].get("currency") or company.reporting_currency or "KRW").strip() if rows else "KRW"
        source_url = f"https://englishdart.fss.or.kr/dsbh001/main.do?rcpNo={filing_no}" if filing_no else None

        enriched = replace(
            company,
            reporting_currency=currency or "KRW",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=self._number(gross_row.get("thstrm_amount")) if gross_row else None,
            operating_income=self._number(operating_row.get("thstrm_amount")) if operating_row else None,
            net_income=net_income,
            net_margin_pct=self._margin(net_income, revenue),
            net_margin_prev_pct=self._margin(net_income_prev, revenue_prev),
            total_assets=self._number(assets_row.get("thstrm_amount")) if assets_row else None,
            total_liabilities=self._number(liabilities_row.get("thstrm_amount")) if liabilities_row else None,
            total_equity=self._number(equity_row.get("thstrm_amount")) if equity_row else None,
            current_assets=self._number(current_assets_row.get("thstrm_amount")) if current_assets_row else None,
            current_liabilities=self._number(current_liabilities_row.get("thstrm_amount")) if current_liabilities_row else None,
            cash_and_equivalents=self._number(cash_row.get("thstrm_amount")) if cash_row else None,
            operating_cash_flow=self._number(ocf_row.get("thstrm_amount")) if ocf_row else None,
            filing_period_end=str(year),
            report_scope="consolidated" if fs_div == "CFS" else "standalone",
            raw_provider_fields={**company.raw_provider_fields, "opendart_corp_code": corp_code, "opendart_receipt_no": filing_no or None},
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_xbrl",
            source_id=filing_no or corp_code,
            source_url=source_url,
            period_end=str(year),
            quality=1.0,
            notes=f"OpenDART annual statement; scope={fs_div}",
        ))
