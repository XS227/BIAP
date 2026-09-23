"""Official Euronext regulated-equity directory and EOD snapshot.

The public Euronext Live regulated-equities download is a single exchange-wide
CSV containing ISIN, local symbol, market, currency, last/closing price, volume
and turnover. BIAP uses it only for Euronext regulated venues.

For EU market membership ESMA FIRDS remains authoritative: the directory resolves
an already-authoritative FIRDS ISIN to a local ticker. The same official CSV is
also suitable for cheap stage-one EOD screening because it covers the regulated
exchange in one request rather than a hand-maintained symbol shortlist.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec
from .models import GlobalCompany
from .providers import GlobalProviderError


_BASE = "https://live.euronext.com"
_DOWNLOAD = _BASE + "/en/product_directory/data/stocks-euronext-regulated/download"
_PAGE = _BASE + "/en/products/equities/regulated/list"
_USER_AGENT = "BIAP Global official Euronext regulated source (+https://setai.no)"

# The exact regulated venue identifiers used by Euronext Live.
_MARKETS: dict[tuple[str, str], str] = {
    ("FR", "EURONEXT_PARIS"): "XPAR",
    ("IT", "EURONEXT_MILAN"): "MTAA",
    ("NL", "EURONEXT_AMSTERDAM"): "XAMS",
    ("BE", "EURONEXT_BRUSSELS"): "XBRU",
    ("PT", "EURONEXT_LISBON"): "XLIS",
    ("NO", "EURONEXT_OSLO"): "XOSL",
    # Dublin is exposed by Euronext Live as XMSM. It can be used as a resolver/
    # EOD source, but ranking remains blocked until its authoritative common-share
    # membership is independently validated in the BIAP universe layer.
    ("IE", "EURONEXT_DUBLIN"): "XMSM",
}


def _float(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _valid_isin(value: object) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


class EuronextLiveRegulatedClient:
    provider_id = "official-euronext-live-regulated"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) in _MARKETS

    @staticmethod
    def mic(country: str, exchange: str) -> str:
        try:
            return _MARKETS[(country.upper(), exchange.upper())]
        except KeyError as exc:
            raise GlobalProviderError(f"Euronext regulated source is not configured for {country}/{exchange}") from exc

    def _download(self, *, country: str, exchange: str) -> tuple[str, list[dict]]:
        mic = self.mic(country, exchange)
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv,*/*",
            "Referer": _PAGE,
        }
        try:
            response = requests.get(
                _DOWNLOAD,
                params={"mics": mic},
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Euronext regulated directory request failed: {type(exc).__name__}") from exc
        text = response.content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        rows: list[dict] = []
        for raw in reader:
            if not isinstance(raw, dict):
                continue
            isin = _valid_isin(raw.get("ISIN"))
            symbol = str(raw.get("Symbol") or "").strip().upper()
            if not isin or not symbol:
                # The first informational lines below the CSV header contain only
                # one cell and naturally land here; ignore them conservatively.
                continue
            rows.append({
                "name": str(raw.get("Name") or symbol).strip(),
                "isin": isin,
                "symbol": symbol,
                "market": str(raw.get("Market") or "").strip(),
                "currency": str(raw.get("Currency") or "").strip().upper(),
                "open": _float(raw.get("Open Price")),
                "high": _float(raw.get("High Price")),
                "low": _float(raw.get("low Price")),
                "last": _float(raw.get("last Price")),
                "volume": _float(raw.get("Volume")),
                "turnover": _float(raw.get("Turnover")),
                "close": _float(raw.get("Closing Price")),
                "mic": mic,
            })
        if not rows:
            raise GlobalProviderError(f"Euronext regulated directory returned no usable rows for {country}/{exchange}")
        return mic, rows

    def resolve_isins(self, identities: Iterable[dict], *, country: str, exchange: str) -> tuple[dict[str, dict], dict]:
        mic, rows = self._download(country=country, exchange=exchange)
        by_isin: dict[str, list[dict]] = {}
        for row in rows:
            by_isin.setdefault(str(row["isin"]), []).append(row)
        resolved: dict[str, dict] = {}
        ambiguous: dict[str, list[str]] = {}
        wanted = {str(item.get("isin") or "").upper() for item in identities if item.get("isin")}
        for isin in sorted(wanted):
            matches = by_isin.get(isin, [])
            symbols = sorted({str(row.get("symbol") or "").upper() for row in matches if row.get("symbol")})
            if len(symbols) != 1:
                if len(symbols) > 1:
                    ambiguous[isin] = symbols
                continue
            chosen = next(row for row in matches if str(row.get("symbol") or "").upper() == symbols[0])
            resolved[isin] = {
                "ticker": symbols[0],
                "name": chosen.get("name"),
                "resolver": self.provider_id,
                "resolverMic": mic,
                "market": chosen.get("market"),
            }
        return resolved, {
            "directoryRows": len(rows),
            "directoryMatched": len(resolved),
            "directoryAmbiguous": len(ambiguous),
            "directoryAmbiguousSample": list(ambiguous.items())[:20],
            "directoryMic": mic,
        }

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        selected = list(instruments)
        mic, rows = self._download(country=country, exchange=spec.code)
        by_isin: dict[str, list[dict]] = {}
        for row in rows:
            by_isin.setdefault(str(row["isin"]), []).append(row)

        quotes: list[dict] = []
        for company in selected:
            isin = str(company.isin or "").strip().upper()
            if not isin:
                continue
            matches = by_isin.get(isin, [])
            # Exact ISIN is the identity key. Reject ambiguous directory rows.
            symbols = {str(row.get("symbol") or "").strip().upper() for row in matches if row.get("symbol")}
            if len(symbols) != 1:
                continue
            row = next(row for row in matches if str(row.get("symbol") or "").strip().upper() in symbols)
            price = row.get("last") or row.get("close")
            if price is None or float(price) <= 0:
                continue
            volume = row.get("volume")
            # Zero-volume but priced securities were still observed in the
            # exchange-wide EOD snapshot. Keep them screened with zero liquidity;
            # they naturally fall to the bottom of the stage-one shortlist.
            effective_volume = max(0.0, float(volume or 0.0))
            high = row.get("high")
            low = row.get("low")
            range_position = None
            if high is not None and low is not None and float(high) > float(low):
                range_position = max(0.0, min(1.0, (float(price) - float(low)) / (float(high) - float(low))))
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": float(price),
                "averageVolume": effective_volume,
                "liquidityValue": float(row.get("turnover") or (float(price) * effective_volume)),
                "rangePosition": range_position,
                "quoteDate": None,
                "mic": mic,
                "provider": self.provider_id,
                "isin": isin,
                "directorySymbol": row.get("symbol"),
            })
        errors: list[str] = []
        if not quotes:
            errors.append(f"Euronext regulated EOD returned no usable FIRDS-universe matches for {country}/{spec.code}")
        return quotes, errors, f"Euronext regulated official EOD ({mic})"
