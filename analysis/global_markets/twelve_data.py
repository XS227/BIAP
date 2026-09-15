"""Twelve Data market adapter for BIAP Global.

This adapter is optional and credential-free in source control: the API key is
read from `BIAP_GLOBAL_MARKET_API_KEY`. It uses daily time-series data to
normalize price/history metrics across supported exchanges. Production use must
respect the provider's plan and exchange-licensing terms.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
import os
import statistics
from typing import Any, Optional

import httpx

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

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        params: dict[str, Any] = {
            "symbol": company.ticker,
            "interval": "1day",
            "outputsize": 260,
            "order": "DESC",
            "format": "JSON",
        }
        if company.exchange:
            params["exchange"] = company.exchange
        if company.country:
            params["country"] = company.country

        payload = self._get("time_series", params)
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise GlobalProviderError(f"no daily market history returned for {company.identity()}")

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
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        currency = str(meta.get("currency") or company.currency or "").strip() or company.currency

        enriched = replace(
            company,
            currency=currency,
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
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="daily_market_history",
                source_id=company.identity(),
                observed_at=enriched.price_observed_at,
                quality=0.9,
                notes="normalized from provider daily time-series; exchange licensing may apply",
            ),
        )
