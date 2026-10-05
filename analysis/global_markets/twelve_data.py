"""Twelve Data market/valuation adapter for BIAP Global.

Credentials are runtime-only (`BIAP_GLOBAL_MARKET_API_KEY`). Daily history is
split-adjusted. Exchange identity is checked against configured operating and
segment MIC aliases. Vendor valuation/profile data is supplementary only;
EvidenceAgent still requires separate official filing evidence before a BUY
candidate can pass.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
import os
import statistics
from typing import Any, Optional

import httpx

from .country_packs import ExchangeSpec, get_exchange
from .history_store import persist_daily_history
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider, append_source

DEFAULT_BASE_URL = "https://api.twelvedata.com"


class TwelveDataMarketProvider(MarketDataProvider):
    provider_id = "twelve-data"

    def __init__(self, *, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 12.0) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("BIAP_GLOBAL_MARKET_BASE") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = max(2.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_GLOBAL_MARKET_API_KEY is required for Twelve Data")

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/{endpoint.lstrip('/')}", params={**params, "apikey": self.api_key})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"Twelve Data request failed for {endpoint}: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError(f"unexpected Twelve Data response for {endpoint}")
        if payload.get("status") == "error" or payload.get("code"):
            raise GlobalProviderError(f"Twelve Data rejected request: {str(payload.get('message') or 'provider error')[:300]}")
        return payload

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _annualized_volatility(closes_desc: list[float]) -> Optional[float]:
        closes = list(reversed(closes_desc))
        returns = [math.log(cur / prev) for prev, cur in zip(closes, closes[1:]) if prev > 0 and cur > 0]
        return statistics.stdev(returns) * math.sqrt(252.0) * 100.0 if len(returns) >= 2 else None

    @staticmethod
    def _max_drawdown(closes_desc: list[float]) -> Optional[float]:
        closes = list(reversed(closes_desc))
        if not closes:
            return None
        peak, worst = closes[0], 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                worst = min(worst, (close - peak) / peak * 100.0)
        return worst

    @staticmethod
    def _period_return(closes_desc: list[float], trading_days: int) -> Optional[float]:
        if not closes_desc:
            return None
        previous = closes_desc[min(trading_days, len(closes_desc) - 1)]
        return (closes_desc[0] / previous - 1.0) * 100.0 if previous > 0 else None

    @staticmethod
    def _observed_at(raw: Any) -> Optional[str]:
        if not raw:
            return None
        text = str(raw).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _exchange_spec(company: GlobalCompany) -> Optional[ExchangeSpec]:
        try:
            return get_exchange(company.country, company.exchange)
        except KeyError:
            return None

    @classmethod
    def _accepted_mics(cls, company: GlobalCompany) -> set[str]:
        spec = cls._exchange_spec(company)
        result = set(spec.accepted_mics) if spec else set()
        if company.mic_code:
            result.add(company.mic_code.strip().upper())
        return result

    @classmethod
    def _query_mic(cls, company: GlobalCompany) -> Optional[str]:
        if company.mic_code:
            return company.mic_code.strip().upper()
        spec = cls._exchange_spec(company)
        return spec.mic.upper() if spec and spec.mic else None

    @classmethod
    def _venue_params(cls, company: GlobalCompany) -> dict[str, str]:
        params: dict[str, str] = {"symbol": company.ticker, "country": company.country.upper()}
        query_mic = cls._query_mic(company)
        if query_mic:
            params["mic_code"] = query_mic
        elif company.exchange:
            params["exchange"] = company.exchange
        return params

    @classmethod
    def _validate_meta(cls, company: GlobalCompany, meta: dict) -> tuple[Optional[str], str]:
        returned_mic = str(meta.get("mic_code") or "").strip().upper() or None
        returned_symbol = str(meta.get("symbol") or company.ticker).strip()
        accepted = cls._accepted_mics(company)
        if returned_mic and accepted and returned_mic not in accepted:
            raise GlobalProviderError(
                f"venue mismatch for {company.ticker}: expected one of {sorted(accepted)}, provider returned {returned_mic}"
            )
        if returned_symbol.upper() != company.ticker.upper():
            raise GlobalProviderError(f"symbol mismatch: requested {company.ticker}, provider returned {returned_symbol}")
        return returned_mic, returned_symbol

    def _add_profile(self, company: GlobalCompany) -> GlobalCompany:
        try:
            payload = self._get("profile", self._venue_params(company))
            self._validate_meta(company, payload)
        except GlobalProviderError as exc:
            return replace(company, raw_provider_fields={**company.raw_provider_fields, "twelve_data_profile_error": str(exc)[:240]})
        return append_source(replace(
            company,
            name=str(payload.get("name") or company.name),
            sector=str(payload.get("sector") or company.sector or "").strip() or None,
            industry=str(payload.get("industry") or company.industry or "").strip() or None,
            instrument_type=str(payload.get("type") or company.instrument_type or "Common Stock"),
            raw_provider_fields={**company.raw_provider_fields, "twelve_data_profile_available": True},
        ), SourceEvidence(
            provider=self.provider_id,
            source_type="vendor_company_profile",
            source_id=company.identity(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            quality=0.80,
            notes="vendor profile supplement; not regulatory filing evidence",
        ))

    def _add_vendor_statistics(self, company: GlobalCompany) -> GlobalCompany:
        try:
            payload = self._get("statistics", self._venue_params(company))
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            self._validate_meta(company, meta)
        except GlobalProviderError as exc:
            return replace(company, raw_provider_fields={**company.raw_provider_fields, "twelve_data_statistics_error": str(exc)[:240]})
        stats = payload.get("statistics") if isinstance(payload.get("statistics"), dict) else {}
        valuation = stats.get("valuations_metrics") if isinstance(stats.get("valuations_metrics"), dict) else {}
        stock_stats = stats.get("stock_statistics") if isinstance(stats.get("stock_statistics"), dict) else {}
        dividends = stats.get("dividends_and_splits") if isinstance(stats.get("dividends_and_splits"), dict) else {}
        enriched = replace(
            company,
            market_cap=company.market_cap or self._float(valuation.get("market_capitalization")),
            shares_outstanding=company.shares_outstanding or self._float(stock_stats.get("shares_outstanding")),
            pe=company.pe or self._float(valuation.get("trailing_pe")),
            pb=company.pb or self._float(valuation.get("price_to_book_mrq")),
            ev_ebitda=company.ev_ebitda or self._float(valuation.get("enterprise_to_ebitda")),
            dividend_yield_pct=company.dividend_yield_pct or self._float(dividends.get("trailing_annual_dividend_yield")),
            raw_provider_fields={**company.raw_provider_fields, "twelve_data_statistics_available": True},
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="vendor_valuation_statistics",
            source_id=enriched.identity(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            quality=0.80,
            notes="vendor-derived valuation supplement; not regulatory filing evidence",
        ))

    def _time_series(self, company: GlobalCompany) -> dict:
        params: dict[str, Any] = {
            **self._venue_params(company),
            "interval": "1day", "outputsize": 260, "order": "DESC", "format": "JSON", "adjust": "splits",
        }
        try:
            payload = self._get("time_series", params)
            if isinstance(payload.get("values"), list) and payload.get("values"):
                return payload
        except GlobalProviderError:
            payload = {}
        # Operating MIC coverage can differ by vendor. If aliases exist, retry by
        # exchange label and validate the returned segment MIC before accepting.
        spec = self._exchange_spec(company)
        if spec and spec.mic_aliases:
            retry = {
                "symbol": company.ticker,
                "exchange": spec.label,
                "country": company.country.upper(),
                "interval": "1day", "outputsize": 260, "order": "DESC", "format": "JSON", "adjust": "splits",
            }
            return self._get("time_series", retry)
        return payload

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        payload = self._time_series(company)
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise GlobalProviderError(f"no daily market history returned for {company.identity()}")
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        returned_mic, _ = self._validate_meta(company, meta)

        rows = [row for row in values if isinstance(row, dict)]
        closes = [value for row in rows if (value := self._float(row.get("close"))) is not None]
        highs = [value for row in rows if (value := self._float(row.get("high"))) is not None]
        lows = [value for row in rows if (value := self._float(row.get("low"))) is not None]
        volumes = [value for row in rows[:30] if (value := self._float(row.get("volume"))) is not None]
        if not closes:
            raise GlobalProviderError(f"no verified close prices returned for {company.identity()}")
        latest = rows[0]
        persist_daily_history(
            company,
            self.provider_id,
            (
                {
                    "date": row.get("datetime"),
                    "open": self._float(row.get("open")),
                    "high": self._float(row.get("high")),
                    "low": self._float(row.get("low")),
                    "close": self._float(row.get("close")),
                    "adjusted_close": self._float(row.get("close")),
                    "volume": self._float(row.get("volume")),
                }
                for row in rows
            ),
            metadata={
                "mic": returned_mic or self._query_mic(company),
                "adjustment": "splits",
            },
        )
        enriched = replace(
            company,
            currency=str(meta.get("currency") or company.currency or "").strip() or company.currency,
            mic_code=returned_mic or self._query_mic(company) or company.mic_code,
            instrument_type=str(meta.get("type") or company.instrument_type or "Common Stock"),
            price=self._float(latest.get("close")),
            price_observed_at=self._observed_at(latest.get("datetime")),
            volume_today=self._float(latest.get("volume")),
            avg_volume_30d=(sum(volumes) / len(volumes) if volumes else None),
            price_52w_high=max(highs) if highs else None,
            price_52w_low=min(lows) if lows else None,
            volatility_annualized_pct=self._annualized_volatility(closes),
            max_drawdown_pct=self._max_drawdown(closes),
            return_1m_pct=self._period_return(closes, 21),
            return_3m_pct=self._period_return(closes, 63),
            return_6m_pct=self._period_return(closes, 126),
            raw_provider_fields={**company.raw_provider_fields, "twelve_data_meta": meta, "price_adjustment": "splits"},
        )
        enriched = append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="daily_market_history",
            source_id=enriched.identity(),
            observed_at=enriched.price_observed_at,
            quality=0.90,
            notes="MIC-qualified, split-adjusted daily history; exchange licensing may apply",
        ))
        enriched = self._add_profile(enriched)
        return self._add_vendor_statistics(enriched)
