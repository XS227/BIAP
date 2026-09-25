"""Public secondary daily market-history fallback for BIAP Global.

This adapter is intentionally lower-trust than the licensed Twelve Data path.
It uses Yahoo Finance's public chart endpoint without authentication and is
registered only for a small explicitly supported set of markets (US, GB, NO)
when no licensed market credential is configured.

Important controls:
- server-side only; no browser/CORS dependency;
- venue and quote-currency checks reject obvious cross-listing mismatches;
- no valuation/fundamental fields are invented;
- provenance explicitly says this is a secondary public source;
- PersistentMarketProvider caches successful verified snapshots and preserves
  their original observation timestamp;
- a future licensed feed automatically supersedes this fallback.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
import statistics
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .country_packs import get_exchange
from .history_store import persist_daily_history
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider, append_source

DEFAULT_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

_SUFFIX = {
    "US": "",
    "GB": ".L",
    "NO": ".OL",
}

_EXPECTED_EXCHANGE_CODES = {
    ("US", "NASDAQ"): {"NMS", "NGM", "NCM", "NAS", "NASDAQ"},
    ("US", "NYSE"): {"NYQ", "NYE", "NYSE"},
    ("GB", "LSE"): {"LSE", "LONDON"},
    ("NO", "EURONEXT_OSLO"): {"OSL", "OSE", "OSLO"},
}


class YahooChartMarketProvider(MarketDataProvider):
    """Lower-trust no-key EOD fallback for US/LSE/Oslo research previews."""

    provider_id = "yahoo-public-chart"

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = max(3.0, float(timeout))

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        country = country.strip().upper()
        exchange = exchange.strip().upper()
        return country in _SUFFIX and (country, exchange) in _EXPECTED_EXCHANGE_CODES

    @staticmethod
    def _vendor_symbol(company: GlobalCompany) -> str:
        country = company.country.strip().upper()
        if country not in _SUFFIX:
            raise GlobalProviderError(f"Yahoo public fallback is not enabled for {country}")
        base = company.ticker.strip().upper().replace(".", "-")
        if not base:
            raise GlobalProviderError("ticker is required")
        return base + _SUFFIX[country]

    def _get(self, symbol: str) -> dict:
        url = f"{self.base_url}/{quote(symbol, safe='-.')}"
        params = {
            "range": "1y",
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; BIAP-Global/0.3; +https://biap.dadashi.no)",
        }
        try:
            with httpx.Client(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
                response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"Yahoo chart request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected Yahoo chart response")
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise GlobalProviderError("Yahoo chart payload missing chart object")
        if chart.get("error"):
            error = chart.get("error")
            description = error.get("description") if isinstance(error, dict) else str(error)
            raise GlobalProviderError(f"Yahoo chart rejected request: {str(description)[:240]}")
        return payload

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @staticmethod
    def _annualized_volatility(closes: list[float]) -> Optional[float]:
        returns = [math.log(cur / prev) for prev, cur in zip(closes, closes[1:]) if prev > 0 and cur > 0]
        return statistics.stdev(returns) * math.sqrt(252.0) * 100.0 if len(returns) >= 2 else None

    @staticmethod
    def _max_drawdown(closes: list[float]) -> Optional[float]:
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
    def _period_return(closes: list[float], trading_days: int) -> Optional[float]:
        if len(closes) < 2:
            return None
        previous_index = max(0, len(closes) - 1 - trading_days)
        previous = closes[previous_index]
        current = closes[-1]
        return (current / previous - 1.0) * 100.0 if previous > 0 and current > 0 else None

    @staticmethod
    def _observed_at(timestamp: Any) -> Optional[str]:
        try:
            raw = int(timestamp)
        except (TypeError, ValueError):
            return None
        if raw <= 0:
            return None
        return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()

    @staticmethod
    def _normalized_currency(meta_currency: object) -> tuple[Optional[str], float]:
        text = str(meta_currency or "").strip()
        upper = text.upper()
        # Preserve the vendor's case long enough to distinguish GBp (pence)
        # from GBP (pounds). Upper-casing first would collapse both into GBP.
        if text == "GBp" or upper in {"GBX", "GBPENCE", "GBPENNY"}:
            return "GBP", 0.01
        if upper == "GBP":
            return "GBP", 1.0
        # Yahoo quotes JSE instruments in South African cents (ZAc/ZAC).
        # Normalize to ISO ZAR so market values and currency checks are not 100x off.
        if text == "ZAc" or upper == "ZAC":
            return "ZAR", 0.01
        return (upper or None), 1.0

    @classmethod
    def _validate_identity(cls, company: GlobalCompany, meta: dict) -> tuple[str, float]:
        country = company.country.strip().upper()
        exchange = company.exchange.strip().upper()
        if not cls.supported(country, exchange):
            raise GlobalProviderError(f"Yahoo public fallback is not enabled for {country}/{exchange}")

        returned_exchange = str(meta.get("exchangeName") or meta.get("fullExchangeName") or "").strip().upper()
        expected = _EXPECTED_EXCHANGE_CODES.get((country, exchange), set())
        if returned_exchange and expected and not any(token in returned_exchange for token in expected):
            raise GlobalProviderError(
                f"venue mismatch for {company.ticker}: expected {country}/{exchange}, provider returned {returned_exchange}"
            )

        currency, scale = cls._normalized_currency(meta.get("currency") or company.currency)
        spec = get_exchange(country, exchange)
        expected_currencies = {value.upper() for value in spec.currencies}
        if currency and expected_currencies and currency not in expected_currencies:
            raise GlobalProviderError(
                f"currency mismatch for {company.ticker}: expected {sorted(expected_currencies)}, provider returned {currency}"
            )
        return currency or company.currency, scale

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        vendor_symbol = self._vendor_symbol(company)
        payload = self._get(vendor_symbol)
        chart = payload["chart"]
        results = chart.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise GlobalProviderError(f"Yahoo returned no chart result for {company.identity()}")
        result = results[0]
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        currency, price_scale = self._validate_identity(company, meta)

        timestamps = result.get("timestamp")
        indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
        quote_rows = indicators.get("quote") if isinstance(indicators.get("quote"), list) else []
        quote_row = quote_rows[0] if quote_rows and isinstance(quote_rows[0], dict) else {}
        adj_rows = indicators.get("adjclose") if isinstance(indicators.get("adjclose"), list) else []
        adj_values = adj_rows[0].get("adjclose") if adj_rows and isinstance(adj_rows[0], dict) else None
        if not isinstance(timestamps, list) or not timestamps or not isinstance(quote_row, dict):
            raise GlobalProviderError(f"Yahoo returned no daily history for {company.identity()}")

        raw_closes = quote_row.get("close") if isinstance(quote_row.get("close"), list) else []
        highs = quote_row.get("high") if isinstance(quote_row.get("high"), list) else []
        lows = quote_row.get("low") if isinstance(quote_row.get("low"), list) else []
        volumes = quote_row.get("volume") if isinstance(quote_row.get("volume"), list) else []

        bars: list[dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            close = self._float(raw_closes[index]) if index < len(raw_closes) else None
            if close is None or close <= 0:
                continue
            adjusted = self._float(adj_values[index]) if isinstance(adj_values, list) and index < len(adj_values) else None
            high = self._float(highs[index]) if index < len(highs) else None
            low = self._float(lows[index]) if index < len(lows) else None
            bars.append({
                "timestamp": timestamp,
                "close": close * price_scale,
                "adjusted": (adjusted if adjusted and adjusted > 0 else close) * price_scale,
                "high": high * price_scale if high is not None else None,
                "low": low * price_scale if low is not None else None,
                "volume": self._float(volumes[index]) if index < len(volumes) else None,
            })
        if not bars:
            raise GlobalProviderError(f"Yahoo returned no verified close prices for {company.identity()}")

        latest = bars[-1]
        observed_at = self._observed_at(latest["timestamp"])
        if not observed_at:
            raise GlobalProviderError(f"Yahoo returned no valid price timestamp for {company.identity()}")
        adjusted_closes = [bar["adjusted"] for bar in bars if isinstance(bar.get("adjusted"), (int, float)) and bar["adjusted"] > 0]
        valid_highs = [bar["high"] for bar in bars if isinstance(bar.get("high"), (int, float)) and bar["high"] > 0]
        valid_lows = [bar["low"] for bar in bars if isinstance(bar.get("low"), (int, float)) and bar["low"] > 0]
        recent_volumes = [bar["volume"] for bar in bars[-30:] if isinstance(bar.get("volume"), (int, float)) and bar["volume"] >= 0]

        persist_daily_history(
            replace(company, currency=currency),
            self.provider_id,
            (
                {
                    "timestamp": bar.get("timestamp"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "adjusted_close": bar.get("adjusted"),
                    "volume": bar.get("volume"),
                }
                for bar in bars
            ),
            metadata={
                "vendorSymbol": vendor_symbol,
                "priceScale": price_scale,
                "adjustment": "adjusted-close-when-available",
            },
        )

        enriched = replace(
            company,
            currency=currency,
            price=float(latest["close"]),
            price_observed_at=observed_at,
            volume_today=latest.get("volume"),
            avg_volume_30d=(sum(recent_volumes) / len(recent_volumes) if recent_volumes else None),
            price_52w_high=max(valid_highs) if valid_highs else None,
            price_52w_low=min(valid_lows) if valid_lows else None,
            volatility_annualized_pct=self._annualized_volatility(adjusted_closes),
            max_drawdown_pct=self._max_drawdown(adjusted_closes),
            return_1m_pct=self._period_return(adjusted_closes, 21),
            return_3m_pct=self._period_return(adjusted_closes, 63),
            return_6m_pct=self._period_return(adjusted_closes, 126),
            raw_provider_fields={
                **company.raw_provider_fields,
                "public_market_fallback": True,
                "public_market_vendor_symbol": vendor_symbol,
                "public_market_exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
                "public_market_price_scale": price_scale,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="public_daily_market_history",
            source_id=vendor_symbol,
            source_url=f"https://finance.yahoo.com/quote/{quote(vendor_symbol, safe='-.')}/history/",
            observed_at=observed_at,
            quality=0.72,
            notes=(
                "Secondary public EOD chart source used only because no licensed market feed is configured; "
                "adjusted close is used for return/volatility/drawdown calculations. Production should prefer a licensed feed."
            ),
        ))
