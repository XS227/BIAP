"""Official/public Nasdaq-operated US equity universe and full-market screener.

Membership comes from Nasdaq Trader's symbol directories. NASDAQ uses
nasdaqlisted.txt; NYSE uses otherlisted.txt rows whose listing-exchange code is
N. The adapter removes ETFs, test issues and non-common instruments such as
preferreds, warrants, rights, units, depositary receipts and debt.

Stage-one price/volume comes from Nasdaq.com's full Stock Screener export and is
joined back to the directory symbol. The screener is market-wide and contains
NYSE as well as NASDAQ securities.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import re
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider

_NASDAQ_DIRECTORY = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_DIRECTORY = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_UNIVERSE_PROVIDER = "official-nasdaq-trader-us-equity-directory"
_MARKET_PROVIDER = "official-nasdaq-us-stock-screener"

_EXCLUDED_NAME = re.compile(
    r"(?:"
    r"warrant|rights?\b|units?\b|preferred|preference|\bpfd\b|"
    r"depositary|depository|\bdep\s+shs\b|\badr\b|\bads\b|"
    r"\betf\b|\betn\b|exchange[- ]traded|"
    r"notes?\b|debenture|bond\b|fund\b|certificate|"
    r"subscription|contingent\s+value"
    r")",
    re.IGNORECASE,
)


def _float(value: object) -> Optional[float]:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text or text.upper() in {"N/A", "NA", "--"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _int(value: object) -> Optional[int]:
    number = _float(value)
    return int(number) if number is not None and number >= 0 else None


def _parse_pipe(text: str) -> list[dict]:
    lines = [
        line for line in text.splitlines()
        if line.strip() and not line.startswith("File Creation Time")
    ]
    if len(lines) < 2:
        raise GlobalProviderError("Nasdaq Trader symbol directory is empty")
    return list(csv.DictReader(StringIO("\n".join(lines)), delimiter="|"))


def _ordinary_security(symbol: str, name: str, *, etf: str, test_issue: str) -> bool:
    symbol = symbol.strip().upper()
    name = name.strip()
    if not symbol or not name:
        return False
    if test_issue.strip().upper() == "Y" or etf.strip().upper() == "Y":
        return False
    if "$" in symbol:
        return False
    if _EXCLUDED_NAME.search(name):
        return False
    return True


def _symbol_variants(symbol: str) -> tuple[str, ...]:
    raw = symbol.strip().upper()
    variants = [
        raw,
        raw.replace(".", "/"),
        raw.replace("-", "/"),
        raw.replace("^", "/"),
        raw.replace("/", "."),
    ]
    return tuple(dict.fromkeys(value for value in variants if value))


class NasdaqTraderUSUniverseProvider(InstrumentUniverseProvider):
    provider_id = _UNIVERSE_PROVIDER

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = max(5.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return country.upper() == "US" and exchange.upper() in {"NASDAQ", "NYSE"}

    def _download(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/plain,*/*"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Nasdaq Trader directory failed: {type(exc).__name__}") from exc
        return response.text

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"US official universe is not configured for {country}/{exchange}")
        exchange = exchange.upper()
        url = _NASDAQ_DIRECTORY if exchange == "NASDAQ" else _OTHER_DIRECTORY
        rows = _parse_pipe(self._download(url))
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []

        for row in rows:
            if exchange == "NASDAQ":
                symbol = str(row.get("Symbol") or "").strip().upper()
                if not _ordinary_security(
                    symbol,
                    str(row.get("Security Name") or ""),
                    etf=str(row.get("ETF") or ""),
                    test_issue=str(row.get("Test Issue") or ""),
                ):
                    continue
                raw = {
                    "official_universe": True,
                    "nasdaq_market_category": str(row.get("Market Category") or "").strip() or None,
                    "nasdaq_financial_status": str(row.get("Financial Status") or "").strip() or None,
                    "nasdaq_nextshares": str(row.get("NextShares") or "").strip() or None,
                }
                mic = "XNAS"
                round_lot = _int(row.get("Round Lot Size"))
            else:
                if str(row.get("Exchange") or "").strip().upper() != "N":
                    continue
                symbol = str(row.get("ACT Symbol") or "").strip().upper()
                if not _ordinary_security(
                    symbol,
                    str(row.get("Security Name") or ""),
                    etf=str(row.get("ETF") or ""),
                    test_issue=str(row.get("Test Issue") or ""),
                ):
                    continue
                raw = {
                    "official_universe": True,
                    "nasdaq_listing_exchange_code": "N",
                    "nasdaq_cqs_symbol": str(row.get("CQS Symbol") or "").strip() or None,
                    "nasdaq_symbol": str(row.get("NASDAQ Symbol") or "").strip() or None,
                }
                mic = "XNYS"
                round_lot = _int(row.get("Round Lot Size"))

            name = str(row.get("Security Name") or symbol).strip()
            result.append(GlobalCompany(
                country="US",
                exchange=exchange,
                currency="USD",
                ticker=symbol,
                name=name,
                mic_code=mic,
                instrument_type="Common Stock",
                lot_size=round_lot,
                raw_provider_fields=raw,
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_market_symbol_directory",
                    source_id=f"US:{exchange}:{symbol}",
                    source_url=url,
                    observed_at=observed,
                    quality=1.0,
                    notes=(
                        "Nasdaq Trader official NASDAQ listed-security directory."
                        if exchange == "NASDAQ"
                        else "Nasdaq Trader official other-listed directory; listing exchange code N denotes NYSE."
                    ),
                )],
            ))

        if not result:
            raise GlobalProviderError(f"Nasdaq Trader returned no ordinary equities for US/{exchange}")
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": observed[:10],
            "nativeMic": "XNAS" if exchange == "NASDAQ" else "XNYS",
            "identitySource": "Nasdaq Trader Symbol Directory",
            "sourceUrl": url,
        }
        return result


class NasdaqUSFullScreenerClient:
    provider_id = _MARKET_PROVIDER

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self._cached: Optional[tuple[str, list[dict]]] = None

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return country.upper() == "US" and exchange.upper() in {"NASDAQ", "NYSE"}

    def _rows(self) -> tuple[str, list[dict]]:
        if self._cached is not None:
            return self._cached
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            response = requests.get(_SCREENER, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"Nasdaq full screener failed: {type(exc).__name__}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) < 1_000:
            raise GlobalProviderError("Nasdaq full screener returned an incomplete payload")
        observed = datetime.now(timezone.utc).date().isoformat()
        self._cached = (observed, [row for row in rows if isinstance(row, dict)])
        return self._cached

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        if not self.supported(country, spec.code):
            raise GlobalProviderError(f"Nasdaq full screener is not configured for {country}/{spec.code}")
        observed, rows = self._rows()
        by_symbol = {
            str(row.get("symbol") or "").strip().upper(): row
            for row in rows
            if str(row.get("symbol") or "").strip()
        }
        quotes: list[dict] = []
        for company in instruments:
            row = None
            directory_symbol = company.ticker.upper()
            for candidate in _symbol_variants(directory_symbol):
                if candidate in by_symbol:
                    row = by_symbol[candidate]
                    break
            if row is None:
                continue
            price = _float(row.get("lastsale"))
            if price is None or price <= 0:
                continue
            volume = max(0.0, float(_float(row.get("volume")) or 0.0))
            quotes.append({
                "ticker": directory_symbol,
                "price": price,
                "averageVolume": volume,
                "liquidityValue": price * volume,
                "rangePosition": None,
                "quoteDate": observed,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "sourceUrl": _SCREENER,
                "marketCap": _float(row.get("marketCap")),
                "sector": str(row.get("sector") or "").strip() or None,
                "industry": str(row.get("industry") or "").strip() or None,
                "screenerSymbol": str(row.get("symbol") or "").strip().upper() or None,
                "countryLabel": str(row.get("country") or "").strip() or None,
            })
        errors: list[str] = []
        if not quotes:
            errors.append(f"Nasdaq full screener returned no usable matches for US/{spec.code}")
        return quotes, errors, f"Nasdaq official full Stock Screener ({observed})"
