"""Official Börse Frankfurt historical key-data fundamentals for German equities.

This adapter uses the public Börse Frankfurt historical key-data API as an
official exchange fundamentals source for German listings.

It is deliberately conservative:
* only DE listings with a German ISIN are accepted;
* only the newest annual row is normalized;
* no exact filing-period end is invented when the API only supplies a year;
* audit status remains unknown unless a stronger filing source states it;
* debt/cash-flow fields are not guessed from ambiguous ratios/per-share values.

This can clear false fundamental-source BLOCKs while Evidence may remain WARN
until a stronger ESEF/issuer/IR provider supplies an exact audited period.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import time
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_API_BASE = "https://api.boerse-frankfurt.de/v1/data/historical_key_data"
_API_SALT = "w4icATTGtnjAQMbkL3kJwxLfEAKDa3VU"


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BoerseFrankfurtFundamentalsProvider(FundamentalsProvider):
    provider_id = "official-boerse-frankfurt-historical-key-data"

    def __init__(self, *, timeout: float = 20.0, limit: int = 12) -> None:
        self.timeout = float(timeout)
        self.limit = max(2, int(limit))

    @staticmethod
    def _url(isin: str, limit: int) -> str:
        return f"{_API_BASE}?isin={isin}&limit={limit}"

    @staticmethod
    def _headers(url: str) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        client_date = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        trace = hashlib.md5((client_date + url + _API_SALT).encode("utf-8")).hexdigest()
        security = hashlib.md5(
            time.strftime("%Y%m%d%H%M", time.localtime()).encode("ascii")
        ).hexdigest()
        return {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "BIAP-Global/1.0 official-exchange-fundamentals",
            "Client-Date": client_date,
            "X-Client-TraceId": trace,
            "X-Security": security,
        }

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                headers=self._headers(url),
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise GlobalProviderError(
                f"Börse Frankfurt historical key-data request failed: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError(
                "Börse Frankfurt historical key-data payload is not an object"
            )
        return payload

    @staticmethod
    def _row(payload: dict[str, Any]) -> dict[str, Any]:
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise GlobalProviderError(
                "Börse Frankfurt historical key-data has no data rows"
            )
        valid = [
            row for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("year"), (int, float))
        ]
        if not valid:
            raise GlobalProviderError(
                "Börse Frankfurt historical key-data has no annual rows"
            )
        return max(valid, key=lambda row: int(row.get("year") or 0))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "DE":
            raise GlobalProviderError(
                "Börse Frankfurt fundamentals apply to DE listings only"
            )
        isin = (company.isin or "").upper().strip()
        if not isin.startswith("DE") or len(isin) != 12:
            raise GlobalProviderError(
                f"Börse Frankfurt fundamentals require a German ISIN, got {isin or 'missing'}"
            )

        url = self._url(isin, self.limit)
        payload = self._get_json(url)
        payload_isin = str(payload.get("isin") or "").upper().strip()
        if payload_isin and payload_isin != isin:
            raise GlobalProviderError(
                f"Börse Frankfurt historical key-data ISIN mismatch: {payload_isin} != {isin}"
            )

        row = self._row(payload)
        year = int(row["year"])
        rows = [
            r for r in (payload.get("data") or [])
            if isinstance(r, dict) and isinstance(r.get("year"), (int, float))
        ]
        previous = next(
            (r for r in rows if int(r.get("year") or 0) == year - 1),
            None,
        )

        revenue = _number(row.get("salesRevenue"))
        revenue_prev = _number(previous.get("salesRevenue")) if previous else None
        net_income = _number(row.get("incomeNet"))
        total_assets = _number(row.get("assetsTotal"))
        total_liabilities = _number(row.get("liabilitiesTotal"))
        total_equity = _number(row.get("equityTotal"))

        minimum = {
            "revenue": revenue,
            "net_income": net_income,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
        }
        if sum(value is not None for value in minimum.values()) < 4:
            raise GlobalProviderError(
                f"Börse Frankfurt FY{year} key data lacks minimum core fundamentals"
            )

        if (
            total_assets is not None
            and total_liabilities is not None
            and total_equity is not None
        ):
            gap = abs(total_assets - (total_liabilities + total_equity))
            scale = max(abs(total_assets), 1.0)
            if gap / scale > 0.08:
                raise GlobalProviderError(
                    f"Börse Frankfurt FY{year} accounting identity mismatch "
                    f"({gap / scale:.2%})"
                )

        shares = _number(row.get("outstandingShares"))
        dividend_per_share = _number(row.get("dividendPerShare"))
        dividend_yield = _number(row.get("dividendReturnRatio"))
        pe = _number(row.get("priceEarningsRatio"))
        pb = _number(row.get("priceBookRatio"))

        raw = {
            **company.raw_provider_fields,
            "de_bf_historical_key_data": True,
            "de_bf_report_year": year,
            "de_bf_period_granularity": "year_only",
            "de_bf_exact_period_end_available": False,
            "de_bf_source_url": url,
        }

        enriched = replace(
            company,
            reporting_currency=str(
                row.get("currencyCode")
                or company.reporting_currency
                or company.currency
            ),
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=(
                ((revenue / revenue_prev) - 1.0) * 100.0
                if revenue is not None and revenue_prev not in (None, 0)
                else None
            ),
            gross_profit=_number(row.get("profitGross")),
            operating_income=_number(row.get("incomeOperating")),
            net_income=net_income,
            net_margin_pct=(
                (net_income / revenue) * 100.0
                if net_income is not None and revenue not in (None, 0)
                else None
            ),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            current_assets=_number(row.get("assetsCurrentTotal")),
            current_liabilities=_number(row.get("liabilitiesCurrentTotal")),
            eps=_number(row.get("earningsPerShareBasic")),
            book_value_per_share=_number(row.get("bookvaluePerShare")),
            pe=pe if company.pe is None else company.pe,
            pb=pb if company.pb is None else company.pb,
            dividend_per_share=(
                dividend_per_share
                if company.dividend_per_share is None
                else company.dividend_per_share
            ),
            dividend_yield_pct=(
                dividend_yield
                if company.dividend_yield_pct is None
                else company.dividend_yield_pct
            ),
            shares_outstanding=(
                shares
                if company.shares_outstanding is None
                else company.shares_outstanding
            ),
            filing_period_end=company.filing_period_end,
            filing_observed_at=company.filing_observed_at,
            raw_provider_fields=raw,
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_fundamental_metrics",
                source_id=f"BF-HKD:{isin}:FY{year}",
                source_url=url,
                observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                period_end=None,
                quality=0.96,
                notes=(
                    f"Börse Frankfurt official historical key data FY{year}; "
                    "exact fiscal period end is not supplied by this endpoint"
                ),
                provenance_status="independently_verified",
                audit_status="unknown",
            ),
        )
