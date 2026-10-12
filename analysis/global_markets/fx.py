"""FX conversion support for BIAP Global portfolio allocation."""

from __future__ import annotations

import os
from typing import Iterable, Optional

import httpx

from .providers import GlobalProviderError


class TwelveDataFXProvider:
    provider_id = "twelve-data-fx"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 10.0) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.base_url = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")
        self.timeout = max(2.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_GLOBAL_MARKET_API_KEY is required for FX conversion")

    def rate(self, base_currency: str, quote_currency: str) -> float:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        if base == quote:
            return 1.0
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(
                    f"{self.base_url}/exchange_rate",
                    params={"symbol": f"{base}/{quote}", "apikey": self.api_key},
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"FX request failed for {base}/{quote}: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError(f"invalid FX response for {base}/{quote}")
        try:
            rate = float(payload.get("rate"))
        except (TypeError, ValueError) as exc:
            raise GlobalProviderError(f"missing FX rate for {base}/{quote}") from exc
        if rate <= 0:
            raise GlobalProviderError(f"invalid FX rate for {base}/{quote}")
        return rate

    def to_base_rates(self, currencies: Iterable[str], base_currency: str) -> dict[str, float]:
        """Return quote-currency -> base-currency rate used by PortfolioAgent.

        Example: SEK -> EUR means one SEK expressed in EUR, so request SEK/EUR.
        """
        base = base_currency.strip().upper()
        result = {base: 1.0}
        for currency in sorted({value.strip().upper() for value in currencies if value.strip()}):
            if currency == base:
                continue
            result[currency] = self.rate(currency, base)
        return result


ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_MAX_AGE_DAYS = 7  # reference rates are published on TARGET business days only


class ECBReferenceFXProvider:
    """ECB euro foreign exchange reference rates (official, free, no key).

    One ECB quote is "units of CUR per 1 EUR"; any pair is the exact cross of two
    quotes (EUR itself is 1). The rate date is recorded and rates older than
    ``ECB_MAX_AGE_DAYS`` are refused, so a portfolio never silently converts with
    an old rate. Currencies the ECB does not publish raise instead of defaulting.
    """

    provider_id = "ecb-euro-reference-rates"
    _cache: Optional[tuple[float, str, dict[str, float]]] = None

    def __init__(self, *, timeout: float = 10.0, ttl_seconds: float = 6 * 3600) -> None:
        self.timeout = max(2.0, float(timeout))
        self.ttl = ttl_seconds
        self.rate_date: Optional[str] = None

    def _table(self) -> tuple[str, dict[str, float]]:
        import re
        import time
        from datetime import date

        cached = ECBReferenceFXProvider._cache
        if cached and time.monotonic() - cached[0] < self.ttl:
            return cached[1], cached[2]
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/xml"}) as client:
                response = client.get(ECB_DAILY_URL)
            response.raise_for_status()
            text = response.text
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"ECB reference rates request failed: {type(exc).__name__}") from exc
        day = re.search(r"<Cube\s+time=['\"](\d{4}-\d{2}-\d{2})['\"]", text)
        rows = re.findall(r"<Cube\s+currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]", text)
        if not day or not rows:
            raise GlobalProviderError("ECB reference rates response had no rates")
        age = (date.today() - date.fromisoformat(day.group(1))).days
        if age > ECB_MAX_AGE_DAYS:
            raise GlobalProviderError(f"ECB reference rates are stale ({day.group(1)}, {age} days old)")
        table = {code: float(rate) for code, rate in rows if float(rate) > 0}
        table["EUR"] = 1.0
        ECBReferenceFXProvider._cache = (time.monotonic(), day.group(1), table)
        return day.group(1), table

    def rate(self, base_currency: str, quote_currency: str) -> float:
        """Value of 1 ``base_currency`` expressed in ``quote_currency``."""
        base, quote = base_currency.strip().upper(), quote_currency.strip().upper()
        if base == quote:
            return 1.0
        day, table = self._table()
        self.rate_date = day
        for code in (base, quote):
            if code not in table:
                raise GlobalProviderError(f"ECB publishes no reference rate for {code}")
        # quote-per-EUR / base-per-EUR
        return table[quote] / table[base]

    def source_info(self) -> dict:
        return {"provider": self.provider_id, "rateDate": self.rate_date, "url": ECB_DAILY_URL}
