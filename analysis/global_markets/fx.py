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
