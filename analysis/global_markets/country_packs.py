"""Country/exchange routing metadata for BIAP Global.

Country packs contain no investment logic and no credentials. They describe
which venues a user can select, which normalized provider family should be used,
and which official disclosure system is the preferred evidence source.

MIC values use ISO 10383 identifiers where BIAP has a verified operating/market
MIC. A missing MIC is safer than guessing one; provider discovery can resolve it
before analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExchangeSpec:
    code: str
    label: str
    currencies: tuple[str, ...]
    mic: Optional[str] = None


@dataclass(frozen=True)
class CountryPack:
    country: str
    name: str
    exchanges: tuple[ExchangeSpec, ...]
    market_provider: str
    fundamentals_provider: str
    filings_provider: str
    official_evidence_source: str
    benchmark_symbols: tuple[str, ...] = ()
    broker_family: str = "broker-adapter"
    enabled: bool = True


E = ExchangeSpec

COUNTRY_PACKS: dict[str, CountryPack] = {
    # Iran is available inside Global without changing the Iran production path.
    "IR": CountryPack("IR", "Iran", (
        E("TSE", "Tehran Stock Exchange", ("IRR",)),
        E("IFB", "Iran Fara Bourse", ("IRR",)),
        E("IFB_BASE", "Iran Fara Bourse Base Market", ("IRR",)),
    ), "iran-market-adapter", "codal", "codal", "CODAL + TSETMC", ("TEDPIX",), "iran-broker-adapter"),

    "US": CountryPack("US", "United States", (
        E("NASDAQ", "Nasdaq", ("USD",), "XNAS"),
        E("NYSE", "New York Stock Exchange", ("USD",), "XNYS"),
    ), "twelve-data", "sec-edgar-xbrl", "sec-edgar-xbrl", "SEC EDGAR", ("SPY", "QQQ"), "ibkr"),
    "CA": CountryPack("CA", "Canada", (
        E("TSX", "Toronto Stock Exchange", ("CAD",), "XTSE"),
        E("TSXV", "TSX Venture Exchange", ("CAD",), "XTSX"),
    ), "twelve-data", "sedar-plus", "sedar-plus", "SEDAR+", ("XIU",), "ibkr"),
    "GB": CountryPack("GB", "United Kingdom", (
        E("LSE", "London Stock Exchange", ("GBP",), "XLON"),
    ), "twelve-data", "uk-filings", "uk-filings", "Companies House + issuer/RNS filings", ("ISF",), "ibkr"),

    # Nordic markets.
    "SE": CountryPack("SE", "Sweden", (
        E("NASDAQ_STOCKHOLM", "Nasdaq Stockholm", ("SEK",), "XSTO"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Nasdaq Nordic + ESEF/issuer filings", ("OMXS30",), "ibkr"),
    "NO": CountryPack("NO", "Norway", (
        E("EURONEXT_OSLO", "Euronext Oslo Børs", ("NOK",), "XOSL"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext/issuer filings + ESEF", ("OSEBX",), "ibkr"),
    "DK": CountryPack("DK", "Denmark", (
        E("NASDAQ_COPENHAGEN", "Nasdaq Copenhagen", ("DKK",), "XCSE"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Nasdaq Nordic + ESEF/issuer filings", ("OMXC25",), "ibkr"),
    "FI": CountryPack("FI", "Finland", (
        E("NASDAQ_HELSINKI", "Nasdaq Helsinki", ("EUR",), "XHEL"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Nasdaq Nordic + ESEF/issuer filings", ("OMXH25",), "ibkr"),
    "IS": CountryPack("IS", "Iceland", (
        E("NASDAQ_ICELAND", "Nasdaq Iceland", ("ISK",), "XICE"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Nasdaq Nordic + issuer filings", (), "ibkr"),

    # Euronext / major European venues.
    "NL": CountryPack("NL", "Netherlands", (
        E("EURONEXT_AMSTERDAM", "Euronext Amsterdam", ("EUR",), "XAMS"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("AEX",), "ibkr"),
    "FR": CountryPack("FR", "France", (
        E("EURONEXT_PARIS", "Euronext Paris", ("EUR",), "XPAR"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("CAC40",), "ibkr"),
    "BE": CountryPack("BE", "Belgium", (
        E("EURONEXT_BRUSSELS", "Euronext Brussels", ("EUR",), "XBRU"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("BEL20",), "ibkr"),
    "IE": CountryPack("IE", "Ireland", (
        E("EURONEXT_DUBLIN", "Euronext Dublin", ("EUR",), "XMSM"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("ISEQ",), "ibkr"),
    "PT": CountryPack("PT", "Portugal", (
        E("EURONEXT_LISBON", "Euronext Lisbon", ("EUR",), "XLIS"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("PSI",), "ibkr"),
    "IT": CountryPack("IT", "Italy", (
        E("EURONEXT_MILAN", "Euronext Milan", ("EUR",), "XMIL"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Euronext + ESEF/issuer filings", ("FTSEMIB",), "ibkr"),
    "DE": CountryPack("DE", "Germany", (
        E("XETRA", "Xetra", ("EUR",), "XETR"),
        E("FRANKFURT", "Frankfurt Stock Exchange", ("EUR",), "XFRA"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Issuer/OAM + ESEF filings", ("DAX",), "ibkr"),
    "ES": CountryPack("ES", "Spain", (
        E("BME_MADRID", "Bolsa de Madrid", ("EUR",), "XMAD"),
    ), "twelve-data", "esef-issuer", "esef-issuer", "Issuer/OAM + ESEF filings", ("IBEX35",), "ibkr"),
    "CH": CountryPack("CH", "Switzerland", (
        E("SIX", "SIX Swiss Exchange", ("CHF",), "XSWX"),
    ), "twelve-data", "six-issuer", "six-issuer", "SIX/issuer disclosures", ("SMI",), "ibkr"),

    # Asia-Pacific.
    "AU": CountryPack("AU", "Australia", (
        E("ASX", "Australian Securities Exchange", ("AUD",), "XASX"),
    ), "twelve-data", "asx-issuer", "asx-issuer", "ASX announcements + issuer reports", ("ASX200",), "ibkr"),
    "NZ": CountryPack("NZ", "New Zealand", (
        E("NZX", "New Zealand Exchange", ("NZD",), "XNZE"),
    ), "twelve-data", "nzx-issuer", "nzx-issuer", "NZX issuer disclosures", ("NZX50",), "ibkr"),
    "JP": CountryPack("JP", "Japan", (
        E("TSE_JP", "Tokyo Stock Exchange", ("JPY",), "XTKS"),
    ), "twelve-data", "edinet", "edinet", "FSA EDINET", ("NIKKEI225", "TOPIX"), "ibkr"),
    "KR": CountryPack("KR", "South Korea", (
        E("KRX", "Korea Exchange", ("KRW",), "XKRX"),
    ), "twelve-data", "opendart", "opendart", "Financial Supervisory Service OpenDART", ("KOSPI",), "ibkr"),
    "HK": CountryPack("HK", "Hong Kong", (
        E("HKEX", "Hong Kong Stock Exchange", ("HKD",), "XHKG"),
    ), "twelve-data", "hkexnews", "hkexnews", "HKEXnews", ("HSI",), "ibkr"),
    "SG": CountryPack("SG", "Singapore", (
        E("SGX", "Singapore Exchange", ("SGD",), "XSES"),
    ), "twelve-data", "sgx-issuer", "sgx-issuer", "SGX issuer announcements", ("STI",), "ibkr"),
    "IN": CountryPack("IN", "India", (
        E("NSE", "National Stock Exchange of India", ("INR",), "XNSE"),
        E("BSE", "BSE", ("INR",), "XBOM"),
    ), "twelve-data", "india-exchange-filings", "india-exchange-filings", "NSE/BSE corporate filings", ("NIFTY50", "SENSEX"), "broker-adapter"),

    # Middle East / emerging markets.
    "SA": CountryPack("SA", "Saudi Arabia", (
        E("SAUDI_EXCHANGE", "Saudi Exchange (Tadawul)", ("SAR",), "XSAU"),
    ), "twelve-data", "saudi-exchange", "saudi-exchange", "Saudi Exchange issuer disclosures", ("TASI",), "broker-adapter"),
    "AE": CountryPack("AE", "United Arab Emirates", (
        E("ADX", "Abu Dhabi Securities Exchange", ("AED",)),
        E("DFM", "Dubai Financial Market", ("AED",)),
    ), "twelve-data", "uae-exchange-filings", "uae-exchange-filings", "ADX/DFM issuer disclosures", (), "broker-adapter"),
    "TR": CountryPack("TR", "Türkiye", (
        E("BIST", "Borsa Istanbul", ("TRY",), "XIST"),
    ), "twelve-data", "kap", "kap", "KAP Public Disclosure Platform", ("BIST100",), "broker-adapter"),
    "ZA": CountryPack("ZA", "South Africa", (
        E("JSE", "Johannesburg Stock Exchange", ("ZAR",), "XJSE"),
    ), "twelve-data", "jse-sens", "jse-sens", "JSE SENS/issuer reports", ("TOP40",), "broker-adapter"),
    "BR": CountryPack("BR", "Brazil", (
        E("B3", "B3 Brasil Bolsa Balcão", ("BRL",), "BVMF"),
    ), "twelve-data", "cvm-open-data", "cvm-open-data", "CVM open data + issuer filings", ("IBOV",), "broker-adapter"),
}


def get_country_pack(country: str) -> CountryPack:
    key = country.strip().upper()
    try:
        return COUNTRY_PACKS[key]
    except KeyError as exc:
        raise KeyError(f"BIAP Global country pack is not configured for {country!r}") from exc


def get_exchange(country: str, exchange: str) -> ExchangeSpec:
    pack = get_country_pack(country)
    wanted = exchange.strip().upper()
    for item in pack.exchanges:
        if wanted in {item.code.upper(), (item.mic or "").upper()}:
            return item
    raise KeyError(f"BIAP Global exchange {exchange!r} is not configured for {country!r}")


def country_catalog() -> list[dict]:
    return [
        {
            "country": pack.country,
            "name": pack.name,
            "enabled": pack.enabled,
            "marketProvider": pack.market_provider,
            "fundamentalsProvider": pack.fundamentals_provider,
            "officialEvidenceSource": pack.official_evidence_source,
            "brokerFamily": pack.broker_family,
            "exchanges": [
                {
                    "code": exchange.code,
                    "label": exchange.label,
                    "mic": exchange.mic,
                    "currencies": list(exchange.currencies),
                }
                for exchange in pack.exchanges
            ],
        }
        for _, pack in sorted(COUNTRY_PACKS.items())
    ]
