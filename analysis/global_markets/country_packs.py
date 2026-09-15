"""Initial market metadata for BIAP Global.

Country packs describe routing metadata only. They do not contain investment
logic or credentials. Provider IDs are intentionally declarative so concrete
adapters can be swapped without changing the agent layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryPack:
    country: str
    exchanges: tuple[str, ...]
    currencies: tuple[str, ...]
    market_provider: str
    fundamentals_provider: str
    filings_provider: str
    benchmark_symbols: tuple[str, ...] = ()


COUNTRY_PACKS: dict[str, CountryPack] = {
    "US": CountryPack(
        country="US",
        exchanges=("NASDAQ", "NYSE"),
        currencies=("USD",),
        market_provider="global-market-us",
        fundamentals_provider="sec-xbrl",
        filings_provider="sec-edgar",
        benchmark_symbols=("SPY", "QQQ"),
    ),
    "SE": CountryPack(
        country="SE",
        exchanges=("NASDAQ_STOCKHOLM",),
        currencies=("SEK",),
        market_provider="nasdaq-nordic",
        fundamentals_provider="esef-issuer",
        filings_provider="esef-issuer",
        benchmark_symbols=("OMXS30",),
    ),
    "NO": CountryPack(
        country="NO",
        exchanges=("EURONEXT_OSLO",),
        currencies=("NOK",),
        market_provider="euronext",
        fundamentals_provider="esef-issuer",
        filings_provider="esef-issuer",
        benchmark_symbols=("OSEBX",),
    ),
    "NL": CountryPack(
        country="NL",
        exchanges=("EURONEXT_AMSTERDAM",),
        currencies=("EUR",),
        market_provider="euronext",
        fundamentals_provider="esef-issuer",
        filings_provider="esef-issuer",
        benchmark_symbols=("AEX",),
    ),
    "FR": CountryPack(
        country="FR",
        exchanges=("EURONEXT_PARIS",),
        currencies=("EUR",),
        market_provider="euronext",
        fundamentals_provider="esef-issuer",
        filings_provider="esef-issuer",
        benchmark_symbols=("CAC40",),
    ),
    "DE": CountryPack(
        country="DE",
        exchanges=("XETRA", "FRANKFURT"),
        currencies=("EUR",),
        market_provider="global-market-de",
        fundamentals_provider="esef-issuer",
        filings_provider="esef-issuer",
        benchmark_symbols=("DAX",),
    ),
    "GB": CountryPack(
        country="GB",
        exchanges=("LSE",),
        currencies=("GBP",),
        market_provider="global-market-gb",
        fundamentals_provider="issuer-filings-gb",
        filings_provider="issuer-filings-gb",
        benchmark_symbols=("FTSE100",),
    ),
}


def get_country_pack(country: str) -> CountryPack:
    key = country.strip().upper()
    try:
        return COUNTRY_PACKS[key]
    except KeyError as exc:
        raise KeyError(f"BIAP Global country pack is not configured for {country!r}") from exc
