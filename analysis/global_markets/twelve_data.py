"""Twelve Data market adapter for BIAP Global.

This adapter is optional and credential-free in source control: the API key is
read from `BIAP_GLOBAL_MARKET_API_KEY`. Daily history is explicitly split-
adjusted so technical returns are not corrupted by stock splits. Venue identity
is qualified with ISO 10383 MIC whenever available and mismatched provider
responses are rejected instead of silently analysing the wrong listing.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
import os
import statistics
from typing import Any, Optional

import httpx

from .country_packs import get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider, append_source


DEFAULT_BASE_URL = "https://api.twelvedata.com"


class TwelveDataMarketProvider(MarketDataProvider):
    provider_id = "twelve-data"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 12.0,
    ) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("BIAP_GLOBAL_MARKET_BASE") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = max(2.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_GLOBAL_MARKET_API_KEY is required for Twelve Data")

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict:
        query = {**params, "apikey": self.api_key}
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/{endpoint.lstrip('/')}", params=query)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"Twelve Data request failed for {endpoint}: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError(f"unexpected Twelve Data response for {endpoint}")
        if payload.get("status") == "error" or payload.get("code"):
            message = str(payload.get("message") or "provider error")[:300]
            raise GlobalProviderError(f"Twelve Data rejected request: {message}")
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
        if len(closes) < 3:
            return None
        returns: list[float] = []
        for previous, current in zip(closes, closes[1:]):
            if previous <= 0 or current <= 0:
                continue
            returns.append(math.log(current / previous))
        if len(returns) < 2:
            return None
        return statistics.stdev(returns) * math.sqrt(252.0) * 100.0

    @staticmethod
    def _max_drawdown(closes_desc: list[float]) -> Optional[float]:
        closes = list(reversed(closes_desc))
        if not closes:
            return None
        peak = closes[0]
        worst = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                worst = min(worst, (close - peak) / peak * 100.0)
        return worst

    @staticmethod
    def _period_return(closes_desc: list[float], trading_days: int) -> Optional[float]:
        if not closes_desc:
            return None
        index = min(trading_days, len(closes_desc) - 1)
        previous = closes_desc[index]
        current = closes_desc[0]
        if previous <= 0:
            return None
        return (current / previous - 1.0) * 100.0

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
    def _expected_mic(company: GlobalCompany) -> Optional[str]:
        if company.mic_code:
            return company.mic_code.strip().upper()
        try:
            configured = get_exchange(company.country, company.exchange)
        except KeyError:
            return None
        return configured.mic.upper() if configured.mic else None

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        expected_mic = self._expected_mic(company)
        params: dict[str, Any] = {
            "symbol": company.ticker,
            "interval": "1day",
            "outputsize": 260,
            "order": "DESC",
            "format": "JSON",
            "adjust": "splits",
        }
        if expected_mic:
            params["mic_code"] = expected_mic
        elif company.exchange:
            # Only fall back to exchange name when no verified MIC exists.
            params["exchange"] = company.exchange
        if company.country:
            params["country"] = company.country.upper()

        payload = self._get("time_series", params)
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise GlobalProviderError(f"no daily market history returned for {company.identity()}")

        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        returned_mic = str(meta.get("mic_code") or "").strip().upper() or None
        returned_symbol = str(meta.get("symbol") or company.ticker).strip()
        if expected_mic and returned_mic and returned_mic != expected_mic:
            raise GlobalProviderError(
                f"venue mismatch for {company.ticker}: expected MIC {expected_mic}, provider returned {returned_mic}"
            )
        if returned_symbol.upper() != company.ticker.upper():
            raise GlobalProviderError(
                f"symbol mismatch: requested {company.ticker}, provider returned {returned_symbol}"
            )

        rows = [row for row in values if isinstance(row, dict)]
        closes = [value for row in rows if (value := self._float(row.get("close"))) is not None]
        highs = [value for row in rows if (value := self._float(row.get("high"))) is not None]
        lows = [value for row in rows if (value := self._float(row.get("low"))) is not None]
        volumes = [value for row in rows[:30] if (value := self._float(row.get("volume"))) is not None]
        if not closes:
            raise GlobalProviderError(f"no verified close prices returned for {company.identity()}")

        latest = rows[0]
        latest_close = self._float(latest.get("close"))
        latest_volume = self._float(latest.get("volume"))
        currency = str(meta.get("currency") or company.currency or "").strip() or company.currency

        enriched = replace(
            company,
            currency=currency,
            mic_code=returned_mic or expected_mic or company.mic_code,
            instrument_type=str(meta.get("type") or company.instrument_type or "Common Stock"),
            price=latest_close,
            price_observed_at=self._observed_at(latest.get("datetime")),
            volume_today=latest_volume,
            avg_volume_30d=(sum(volumes) / len(volumes) if volumes else None),
            price_52w_high=max(highs) if highs else None,
            price_52w_low=min(lows) if lows else None,
            volatility_annualized_pct=self._annualized_volatility(closes),
            max_drawdown_pct=self._max_drawdown(closes),
            return_1m_pct=self._period_return(closes, 21),
            return_3m_pct=self._period_return(closes, 63),
            return_6m_pct=self._period_return(closes, 126),
            raw_provider_fields={
                **company.raw_provider_fields,
                "twelve_data_meta": meta,
                "price_adjustment": "splits",
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="daily_market_history",
                source_id=enriched.identity(),
                observed_at=enriched.price_observed_at,
                quality=0.9,
                notes="MIC-qualified, split-adjusted daily history; exchange licensing may apply",
            ),
        )
