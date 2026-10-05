"""Official Nasdaq Nordic Main Market universe and stage-one quotes.

The public Nasdaq Nordic screener exposes exchange-filtered Main Market shares
for Copenhagen, Stockholm, Helsinki and Iceland. BIAP uses the exchange's own
market filter for membership and the same response for stage-one price/volume
screening. No cross-market inference from ISIN prefixes is used.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec, get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_URL = "https://api.nasdaq.com/api/nordic/screener/shares"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
_MARKETS: dict[tuple[str, str], str] = {
    ("SE", "NASDAQ_STOCKHOLM"): "STO",
    ("DK", "NASDAQ_COPENHAGEN"): "CPH",
    ("FI", "NASDAQ_HELSINKI"): "HEL",
    ("IS", "NASDAQ_ICELAND"): "ICE",
}
_DR_RE = re.compile(r"(?:^|[ ._-])(ADR|GDR|SDR|FDR)(?:$|[ ._-])", re.I)
_PREF_RE = re.compile(r"\b(PREF|PREFERENCE|PREFERRED)\b", re.I)


def _number(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if not text or text == "-":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def normalize_nordic_symbol(value: object) -> str:
    text = re.sub(r"\s+", ".", str(value or "").strip().upper())
    return text.strip(".")


def _valid_isin(value: object) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


def _ordinary_share_row(row: dict, spec: ExchangeSpec) -> bool:
    if str(row.get("assetClass") or "").strip().upper() != "SHARES":
        return False
    isin = _valid_isin(row.get("isin"))
    symbol = normalize_nordic_symbol(row.get("symbol"))
    currency = str(row.get("currency") or "").strip().upper()
    name = str(row.get("fullName") or "").strip()
    if not isin or not symbol or not currency:
        return False
    if spec.currencies and currency not in {x.upper() for x in spec.currencies}:
        return False
    upper = name.upper()
    if "DEPOSITARY" in upper or _DR_RE.search(upper) or _PREF_RE.search(upper):
        return False
    return True


class NasdaqNordicOfficialClient:
    provider_id = "official-nasdaq-nordic-main-market"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) in _MARKETS

    @staticmethod
    def market_code(country: str, exchange: str) -> str:
        try:
            return _MARKETS[(country.upper(), exchange.upper())]
        except KeyError as exc:
            raise GlobalProviderError(f"Nasdaq Nordic Main Market is not configured for {country}/{exchange}") from exc

    def _rows(self, *, country: str, exchange: str) -> tuple[list[dict], dict]:
        market = self.market_code(country, exchange)
        params = [
            ("category", "MAIN_MARKET"),
            ("tableonly", "true"),
            ("page", "1"),
            ("size", "1000"),
            ("segment", "LARGE_CAP"),
            ("segment", "MID_CAP"),
            ("segment", "SMALL_CAP"),
            ("segment", "SPAC"),
            ("market", market),
            ("lang", "en"),
        ]
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            response = requests.get(_URL, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"Nasdaq Nordic Main Market request failed: {type(exc).__name__}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        listing = (data or {}).get("instrumentListing") if isinstance(data, dict) else None
        rows = (listing or {}).get("rows") if isinstance(listing, dict) else None
        pagination = (data or {}).get("pagination") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise GlobalProviderError("Nasdaq Nordic Main Market returned an unexpected payload")
        return [row for row in rows if isinstance(row, dict)], dict(pagination or {})

    def eligible_rows(self, *, country: str, exchange: str) -> tuple[list[dict], dict]:
        spec = get_exchange(country, exchange)
        raw, pagination = self._rows(country=country, exchange=exchange)
        eligible = [row for row in raw if _ordinary_share_row(row, spec)]
        if not eligible:
            raise GlobalProviderError(f"Nasdaq Nordic returned no eligible ordinary shares for {country}/{exchange}")
        metadata = {
            "marketCode": self.market_code(country, exchange),
            "sourceTotal": int(pagination.get("total") or len(raw)),
            "officialCount": len(eligible),
            "resolvedCount": len(eligible),
            "resolutionCoveragePct": 100.0,
            "excludedNonOrdinary": max(0, len(raw) - len(eligible)),
            "identitySource": "Nasdaq Nordic official Main Market screener",
        }
        self.last_metadata = metadata
        return eligible, metadata

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        rows, _ = self.eligible_rows(country=country, exchange=spec.code)
        by_isin = {_valid_isin(row.get("isin")): row for row in rows if _valid_isin(row.get("isin"))}
        quotes: list[dict] = []
        for company in instruments:
            isin = _valid_isin(company.isin)
            row = by_isin.get(isin) if isin else None
            if row is None:
                continue
            price = _number(row.get("lastSalePrice"))
            if price is None or price <= 0:
                continue
            volume = max(0.0, float(_number(row.get("volume")) or 0.0))
            turnover = _number(row.get("turnover"))
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": price,
                "averageVolume": volume,
                "liquidityValue": max(0.0, float(turnover or (price * volume))),
                "rangePosition": None,
                "quoteDate": None,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "isin": isin,
                "orderbookId": row.get("orderbookId"),
            })
        errors: list[str] = []
        if not quotes:
            errors.append(f"Nasdaq Nordic Main Market returned no usable prices for {country}/{spec.code}")
        return quotes, errors, f"Nasdaq Nordic official Main Market ({self.market_code(country, spec.code)})"


class NasdaqNordicUniverseProvider(InstrumentUniverseProvider):
    provider_id = NasdaqNordicOfficialClient.provider_id

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.client = NasdaqNordicOfficialClient(timeout=timeout)
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return NasdaqNordicOfficialClient.supported(country, exchange)

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"Nasdaq Nordic universe is not configured for {country}/{exchange}")
        country = country.upper()
        exchange = exchange.upper()
        spec = get_exchange(country, exchange)
        rows, metadata = self.client.eligible_rows(country=country, exchange=exchange)
        self.last_metadata = dict(metadata)
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            isin = _valid_isin(row.get("isin"))
            ticker = normalize_nordic_symbol(row.get("symbol"))
            if not isin or not ticker:
                continue
            result.append(GlobalCompany(
                country=country,
                exchange=exchange,
                currency=str(row.get("currency") or "").strip().upper(),
                ticker=ticker,
                name=str(row.get("fullName") or ticker).strip(),
                mic_code=spec.mic,
                isin=isin,
                instrument_type="Common Stock",
                sector=str(row.get("sector") or "").strip() or None,
                raw_provider_fields={
                    "official_universe": True,
                    "nasdaq_market_code": metadata.get("marketCode"),
                    "nasdaq_orderbook_id": row.get("orderbookId"),
                    "nasdaq_asset_class": row.get("assetClass"),
                    "nasdaq_source_total": metadata.get("sourceTotal"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"NASDAQ-NORDIC:{metadata.get('marketCode')}:{row.get('orderbookId') or isin}",
                    source_url=_URL,
                    observed_at=observed,
                    quality=1.0,
                    notes="Nasdaq Nordic official Main Market share screener; exchange filter determines membership.",
                )],
            ))
        if not result:
            raise GlobalProviderError(f"Nasdaq Nordic universe normalized no shares for {country}/{exchange}")
        self.last_metadata["officialCount"] = len(result)
        self.last_metadata["resolvedCount"] = len(result)
        self.last_metadata["resolutionCoveragePct"] = 100.0
        return result
