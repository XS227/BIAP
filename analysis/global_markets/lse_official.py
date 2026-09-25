"""Official London Stock Exchange Main Market universe and stage-one prices.

BIAP reads the LSE-operated Price Explorer API, keeps ordinary equity listings,
normalizes GBX prices to GBP, and joins stage-one quotes to the official listing
universe by ISIN/TIDM. Depositary receipts, preferreds, warrants, rights and
other non-ordinary instruments are excluded from the ranking universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec, get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_PAGES = "https://api.londonstockexchange.com/api/v1/pages"
_REFRESH = "https://api.londonstockexchange.com/api/v1/components/refresh"
_PATH = "live-markets/market-data-dashboard/price-explorer"
_SOURCE_PAGE = "https://www.londonstockexchange.com/live-markets/market-data-dashboard/price-explorer"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
_PROVIDER_ID = "official-lse-main-market-price-explorer"
_REJECT = re.compile(
    r"\b(GDR|ADR|DEPOSITARY|DEPOSITORY|PREF(?:ERENCE|ERRED)?|WARRANT|RIGHTS?|ETF|ETC|ETN|NOTE|BOND|CERTIFICATE)\b",
    re.I,
)


def _valid_isin(value: object) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


def _number(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _gbp_price(value: object, currency: object) -> Optional[float]:
    number = _number(value)
    if number is None:
        return None
    ccy = str(currency or "").strip().upper()
    if ccy in {"GBX", "GBPX", "GBp".upper()}:
        return number / 100.0
    if ccy == "GBP":
        return number
    return None


def _ordinary_row(row: dict) -> bool:
    if str(row.get("category") or "").strip().upper() != "EQUITY":
        return False
    if not _valid_isin(row.get("isin")):
        return False
    if not str(row.get("tidm") or "").strip():
        return False
    if str(row.get("currency") or "").strip().upper() not in {"GBP", "GBX", "GBPX"}:
        return False
    text = " ".join(
        str(row.get(key) or "")
        for key in ("description", "name", "issuername")
    ).upper()
    if _REJECT.search(text):
        return False
    maturity = str(row.get("maturitydate") or "").strip()
    if maturity:
        return False
    return True


class LSEOfficialClient:
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 60.0, page_size: int = 100) -> None:
        self.timeout = max(15.0, float(timeout))
        self.page_size = max(25, min(int(page_size), 250))
        self._cached: Optional[tuple[str, list[dict], dict]] = None
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("GB", "LSE")

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.londonstockexchange.com",
            "Referer": "https://www.londonstockexchange.com/",
        }

    def _component_id(self, session: requests.Session) -> str:
        params = {
            "path": _PATH,
            "parameters": "markets=MAINMARKET&categories=EQUITY",
        }
        try:
            response = session.get(_PAGES, params=params, headers=self._headers(), timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"LSE Price Explorer pages request failed: {type(exc).__name__}") from exc
        components = payload.get("components") if isinstance(payload, dict) else None
        for component in components or []:
            if isinstance(component, dict) and component.get("type") == "price-explorer" and component.get("id"):
                return str(component["id"])
        raise GlobalProviderError("LSE Price Explorer component id was not found")

    def _page(self, session: requests.Session, component_id: str, page: int) -> dict:
        filters = (
            "markets=MAINMARKET&categories=EQUITY&subcategories=1&"
            f"showonlylse=true&page={page}&size={self.page_size}"
        )
        body = {
            "path": _PATH,
            "parameters": filters,
            "components": [{"componentId": component_id, "parameters": filters}],
        }
        try:
            response = session.post(
                _REFRESH,
                params={"parameters": filters, "path": _PATH, "components": "priceexplorersearch"},
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"LSE Price Explorer refresh failed: {type(exc).__name__}") from exc
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise GlobalProviderError("LSE Price Explorer returned an unexpected refresh payload")
        content = payload[0].get("content")
        if not isinstance(content, list):
            raise GlobalProviderError("LSE Price Explorer refresh has no component content")
        components = {
            str(item.get("name")): item.get("value")
            for item in content
            if isinstance(item, dict) and item.get("name")
        }
        result = components.get("priceexplorersearch")
        if not isinstance(result, dict):
            raise GlobalProviderError("LSE Price Explorer search component is missing")
        return result

    def eligible_rows(self) -> tuple[str, list[dict], dict]:
        if self._cached is not None:
            return self._cached
        session = requests.Session()
        component_id = self._component_id(session)
        first = self._page(session, component_id, 0)
        total_pages = int(first.get("totalPages") or 1)
        source_total = int(first.get("totalElements") or 0)
        raw: list[dict] = [row for row in (first.get("content") or []) if isinstance(row, dict)]
        for page in range(1, total_pages):
            result = self._page(session, component_id, page)
            raw.extend(row for row in (result.get("content") or []) if isinstance(row, dict))

        dedup: dict[tuple[str, str], dict] = {}
        for row in raw:
            if not _ordinary_row(row):
                continue
            isin = _valid_isin(row.get("isin"))
            ticker = str(row.get("tidm") or "").strip().upper()
            if isin and ticker:
                dedup[(isin, ticker)] = row
        rows = list(dedup.values())
        if not rows:
            raise GlobalProviderError("LSE Price Explorer returned no eligible ordinary equities")
        observed = datetime.now(timezone.utc).date().isoformat()
        metadata = {
            "sourceTotal": source_total or len(raw),
            "rawRows": len(raw),
            "officialCount": len(rows),
            "resolvedCount": len(rows),
            "resolutionCoveragePct": 100.0,
            "excludedNonOrdinary": max(0, len(raw) - len(rows)),
            "identitySource": "London Stock Exchange official Main Market Price Explorer",
        }
        self.last_metadata = metadata
        self._cached = (observed, rows, metadata)
        return self._cached

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        if not self.supported(country, spec.code):
            raise GlobalProviderError(f"LSE official market source is not configured for {country}/{spec.code}")
        observed, rows, _ = self.eligible_rows()
        by_key = {
            (_valid_isin(row.get("isin")), str(row.get("tidm") or "").strip().upper()): row
            for row in rows
        }
        by_isin: dict[str, list[dict]] = {}
        for row in rows:
            isin = _valid_isin(row.get("isin"))
            if isin:
                by_isin.setdefault(isin, []).append(row)

        quotes: list[dict] = []
        for company in instruments:
            isin = _valid_isin(company.isin)
            ticker = company.ticker.upper()
            row = by_key.get((isin, ticker)) if isin else None
            if row is None and isin and len(by_isin.get(isin, [])) == 1:
                row = by_isin[isin][0]
            if row is None:
                continue
            price = _gbp_price(row.get("lastprice"), row.get("currency"))
            if price is None or price <= 0:
                continue
            high = _gbp_price(row.get("fiftyTwoWeeksMax"), row.get("currency"))
            low = _gbp_price(row.get("fiftyTwoWeeksMin"), row.get("currency"))
            range_position = None
            if high is not None and low is not None and high > low:
                range_position = max(0.0, min(1.0, (price - low) / (high - low)))
            market_cap = max(0.0, float(_number(row.get("marketcapitalization")) or 0.0))
            quotes.append({
                "ticker": ticker,
                "price": price,
                "averageVolume": 0.0,
                "liquidityValue": market_cap if market_cap > 0 else price,
                "rangePosition": range_position,
                "quoteDate": observed,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "sourceUrl": _SOURCE_PAGE,
                "isin": isin,
                "marketCap": market_cap or None,
                "directoryTicker": str(row.get("tidm") or "").strip().upper() or None,
                "rankMetric": "market_cap",
            })
        errors: list[str] = []
        if not quotes:
            errors.append("LSE official Price Explorer returned no usable ordinary-equity matches")
        return quotes, errors, f"LSE official Main Market Price Explorer ({observed})"


class LSEOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.client = LSEOfficialClient(timeout=timeout)
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return LSEOfficialClient.supported(country, exchange)

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"LSE official universe is not configured for {country}/{exchange}")
        country = country.upper()
        exchange = exchange.upper()
        spec = get_exchange(country, exchange)
        observed_date, rows, metadata = self.client.eligible_rows()
        self.last_metadata = dict(metadata)
        observed_at = f"{observed_date}T00:00:00+00:00"
        result: list[GlobalCompany] = []
        for row in rows:
            isin = _valid_isin(row.get("isin"))
            ticker = str(row.get("tidm") or "").strip().upper()
            if not isin or not ticker:
                continue
            result.append(GlobalCompany(
                country=country,
                exchange=exchange,
                currency="GBP",
                ticker=ticker,
                name=str(row.get("issuername") or row.get("description") or ticker).strip(),
                mic_code=spec.mic,
                isin=isin,
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "lse_description": row.get("description"),
                    "lse_native_currency": row.get("currency"),
                    "lse_issuer_code": row.get("issuercode"),
                    "lse_source_total": metadata.get("sourceTotal"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"LSE:{ticker}:{isin}",
                    source_url=_SOURCE_PAGE,
                    observed_at=observed_at,
                    quality=1.0,
                    notes="London Stock Exchange official Main Market Price Explorer; non-ordinary instruments excluded.",
                )],
            ))
        if not result:
            raise GlobalProviderError("LSE official universe normalized no ordinary equities")
        self.last_metadata["officialCount"] = len(result)
        self.last_metadata["resolvedCount"] = len(result)
        self.last_metadata["resolutionCoveragePct"] = 100.0
        return result
