"""Expanded public daily-history fallback for supported global exchanges.

This keeps BIAP's evidence-first behavior: Yahoo is only a secondary public EOD
source used when no licensed market feed is configured. The adapter never
creates fundamentals or valuation fields, and it only enables venues with a
stable Yahoo symbol suffix mapping. Ambiguous venues stay cache-only.
"""
from __future__ import annotations

from typing import Optional

from .country_packs import get_exchange
from .models import GlobalCompany
from .providers import GlobalProviderError
from .yahoo_chart import YahooChartMarketProvider


# Yahoo suffixes are venue-specific. Existing US/GB/NO mappings remain handled
# by YahooChartMarketProvider itself. These additional venues are deliberately
# limited to suffixes that are stable enough for deterministic routing.
_MARKET_SUFFIX: dict[tuple[str, str], str] = {
    ("AU", "ASX"): ".AX",
    ("JP", "TSE_JP"): ".T",
    ("SE", "NASDAQ_STOCKHOLM"): ".ST",
    ("DK", "NASDAQ_COPENHAGEN"): ".CO",
    ("FI", "NASDAQ_HELSINKI"): ".HE",
    ("IS", "NASDAQ_ICELAND"): ".IC",
    ("NL", "EURONEXT_AMSTERDAM"): ".AS",
    ("FR", "EURONEXT_PARIS"): ".PA",
    ("BE", "EURONEXT_BRUSSELS"): ".BR",
    ("IE", "EURONEXT_DUBLIN"): ".IR",
    ("PT", "EURONEXT_LISBON"): ".LS",
    ("IT", "EURONEXT_MILAN"): ".MI",
    ("DE", "XETRA"): ".DE",
    ("DE", "FRANKFURT"): ".F",
    ("ES", "BME_MADRID"): ".MC",
    ("CH", "SIX"): ".SW",
    ("CA", "TSX"): ".TO",
    ("CA", "TSXV"): ".V",
    ("NZ", "NZX"): ".NZ",
    ("HK", "HKEX"): ".HK",
    ("SG", "SGX"): ".SI",
    ("IN", "NSE"): ".NS",
    ("IN", "BSE"): ".BO",
    ("SA", "SAUDI_EXCHANGE"): ".SR",
    ("TR", "BIST"): ".IS",
    ("ZA", "JSE"): ".JO",
    ("BR", "B3"): ".SA",
}


class RegionalYahooChartMarketProvider(YahooChartMarketProvider):
    """Yahoo EOD fallback covering BIAP's unambiguous global venue mappings."""

    provider_id = "yahoo-public-chart-global"

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        country = country.strip().upper()
        exchange = exchange.strip().upper()
        return YahooChartMarketProvider.supported(country, exchange) or (country, exchange) in _MARKET_SUFFIX

    @staticmethod
    def _vendor_symbol(company: GlobalCompany) -> str:
        country = company.country.strip().upper()
        exchange = company.exchange.strip().upper()
        if YahooChartMarketProvider.supported(country, exchange):
            return YahooChartMarketProvider._vendor_symbol(company)

        suffix = _MARKET_SUFFIX.get((country, exchange))
        if suffix is None:
            raise GlobalProviderError(f"Yahoo public fallback is not enabled for {country}/{exchange}")

        base = company.ticker.strip().upper().replace(".", "-")
        if not base:
            raise GlobalProviderError("ticker is required")

        # Yahoo uses four-digit HK symbols. Reference providers occasionally
        # normalize away leading zeroes, so restore them only for numeric HK rows.
        if country == "HK" and base.isdigit():
            base = base.zfill(4)
        return base + suffix

    @classmethod
    def _validate_identity(cls, company: GlobalCompany, meta: dict) -> tuple[str, float]:
        country = company.country.strip().upper()
        exchange = company.exchange.strip().upper()
        if YahooChartMarketProvider.supported(country, exchange):
            return YahooChartMarketProvider._validate_identity(company, meta)
        if (country, exchange) not in _MARKET_SUFFIX:
            raise GlobalProviderError(f"Yahoo public fallback is not enabled for {country}/{exchange}")

        # The suffix itself selects the venue for these markets. Yahoo's
        # exchangeName vocabulary varies by region, so reject on quote-currency
        # mismatch rather than brittle vendor labels.
        currency, scale = cls._normalized_currency(meta.get("currency") or company.currency)
        spec = get_exchange(country, exchange)
        expected_currencies = {value.upper() for value in spec.currencies}
        if currency and expected_currencies and currency not in expected_currencies:
            raise GlobalProviderError(
                f"currency mismatch for {company.ticker}: expected {sorted(expected_currencies)}, provider returned {currency}"
            )
        return currency or company.currency, scale


def regional_yahoo_markets() -> tuple[tuple[str, str], ...]:
    """Expose deterministic mappings for diagnostics/tests."""
    return tuple(sorted(_MARKET_SUFFIX))
