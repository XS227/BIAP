"""Instrument universe adapters for BIAP Global country/exchange selection.

Reference-data discovery is intentionally separable from price/history access.
Twelve Data documents a public ``demo`` key for the /stocks catalog. BIAP may
use that catalog when no private market-data credential is configured, but the
result is tagged as reference-only evidence and is never treated as a price
feed or sufficient evidence for a BUY recommendation.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

import httpx

from symbol_universe import SymbolUniverseUnavailable, query_symbols

from .country_packs import ExchangeSpec, get_country_pack, get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


def _clean_isin(value: object) -> Optional[str]:
    """Return only a structurally valid ISIN-like identifier."""
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


def _ordinary_equity_row(*, country: str, spec: ExchangeSpec, row: dict, symbol: str, currency: str) -> bool:
    """Conservatively accept only ordinary operating-company equities.

    Vendor reference catalogs occasionally label bonds, preference shares,
    structured products and foreign/international-segment lines as ``Common
    Stock``. Kiasha's stock scanner must not treat those as ordinary shares.
    CFI is authoritative when present; venue-specific ticker/name guards are a
    second line of defence for incomplete vendor rows.
    """
    instrument_type = str(row.get("type") or "Common Stock").strip()
    kind = instrument_type.lower()
    if "stock" not in kind and "equity" not in kind:
        return False

    cfi = str(row.get("cfi_code") or "").strip().upper()
    # ISO 10962 CFI codes for equities start with E. If the vendor supplied a
    # CFI at all, do not override a non-equity classification with a loose
    # textual "Common Stock" label.
    if cfi and not cfi.startswith("E"):
        return False

    allowed_currencies = {value.upper() for value in spec.currencies}
    if country.upper() == "GB":
        # LSE ordinary shares may be catalogued in pounds or pence.
        allowed_currencies.add("GBX")
    if allowed_currencies and currency.upper() not in allowed_currencies:
        return False

    ticker = symbol.strip().upper()
    if not ticker:
        return False
    if ".PR." in ticker or ticker.endswith(".PR") or ".RT." in ticker or ticker.endswith(".RT"):
        return False

    # Numeric-leading XLON symbols are commonly international/structured
    # segments (for example 0A0D/010K/1HP5) rather than the issuer's primary
    # ordinary London line. Do not apply this rule to Oslo, where legitimate
    # ordinary equities such as 2020 Bulkers use numeric tickers.
    if country.upper() == "GB" and ticker[0].isdigit():
        return False

    name = f" {str(row.get('name') or '').upper()} "
    rejected_name_tokens = (
        " FRN ", " FLOATING RATE ", " BOND ", " NOTE ", " NOTES ",
        " WARRANT ", " WARRANTS ", " RIGHTS ", " CERTIFICATE ",
        " PREFERENCE ", " PREFERRED ", " CONVERTIBLE BOND ",
        " ETN ", " ETC ", " STRUCTURED ", " ZERO COUPON ",
        " MEDIUM TERM ", " DEBT SECURITY ",
    )
    return not any(token in name for token in rejected_name_tokens)


class TwelveDataUniverseProvider(InstrumentUniverseProvider):
    provider_id = "twelve-data-universe"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 15.0, max_rows: int = 5000) -> None:
        configured_key = api_key if api_key is not None else os.environ.get("BIAP_GLOBAL_MARKET_API_KEY")
        self.api_key = (configured_key or "demo").strip()
        self.demo_mode = self.api_key.lower() == "demo"
        if self.demo_mode:
            self.provider_id = "twelve-data-universe-demo"
        self.base_url = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")
        self.timeout = max(3.0, float(timeout))
        self.max_rows = max(1, min(int(max_rows), 20000))

    def _request(self, params: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/stocks", params={**params, "apikey": self.api_key})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"instrument universe request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected instrument universe response")
        if payload.get("status") == "error" or payload.get("code"):
            raise GlobalProviderError(str(payload.get("message") or "instrument universe provider error")[:300])
        return payload

    @staticmethod
    def _payload_score(payload: dict) -> tuple[int, int]:
        rows = payload.get("data")
        row_count = len(rows) if isinstance(rows, list) else 0
        try:
            total = int(payload.get("count") or 0)
        except (TypeError, ValueError):
            total = 0
        return row_count, total

    def _get_page(self, *, country: str, spec: ExchangeSpec, page: int, outputsize: int) -> dict:
        common = {"page": page, "outputsize": outputsize, "format": "JSON", "type": "Common Stock"}
        candidates: list[dict] = []

        if spec.mic:
            candidates.append(self._request({**common, "mic_code": spec.mic}))

        country_name = get_country_pack(country).name
        try:
            candidates.append(self._request({**common, "country": country_name, "exchange": spec.label}))
        except GlobalProviderError:
            if not candidates:
                raise

        if not candidates:
            raise GlobalProviderError(f"no reference-data lookup strategy for {country}/{spec.code}")
        return max(candidates, key=self._payload_score)

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if not country or not exchange:
            raise GlobalProviderError("country and exchange are required for bounded instrument discovery")
        spec = get_exchange(country, exchange)
        accepted_mics = set(spec.accepted_mics)
        result: list[GlobalCompany] = []
        seen: set[tuple[str, str]] = set()
        page = 1
        page_size = min(1000, self.max_rows)

        while len(result) < self.max_rows:
            payload = self._get_page(country=country, spec=spec, page=page, outputsize=page_size)
            rows = payload.get("data")
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").strip()
                if not symbol:
                    continue
                returned_mic = str(row.get("mic_code") or "").strip().upper() or None
                if accepted_mics and returned_mic and returned_mic not in accepted_mics:
                    continue
                venue_key = (returned_mic or spec.mic or spec.code).upper()
                dedupe_key = (venue_key, symbol.upper())
                if dedupe_key in seen:
                    continue
                currency = str(row.get("currency") or (spec.currencies[0] if spec.currencies else "")).strip().upper()
                if not currency:
                    continue
                if not _ordinary_equity_row(country=country, spec=spec, row=row, symbol=symbol, currency=currency):
                    continue
                seen.add(dedupe_key)
                instrument_type = str(row.get("type") or "Common Stock").strip()
                result.append(GlobalCompany(
                    country=country.upper(),
                    exchange=spec.code,
                    mic_code=returned_mic or spec.mic,
                    currency=currency,
                    ticker=symbol,
                    name=str(row.get("name") or symbol).strip(),
                    isin=_clean_isin(row.get("isin")),
                    instrument_type=instrument_type or "Common Stock",
                    raw_provider_fields={
                        "figi": str(row.get("figi_code") or "").strip() or None,
                        "cfi": str(row.get("cfi_code") or "").strip() or None,
                        "reference_access": "demo" if self.demo_mode else "authenticated",
                    },
                    sources=[SourceEvidence(
                        provider=self.provider_id,
                        source_type="instrument_reference",
                        source_id=f"{country.upper()}:{returned_mic or spec.mic or spec.code}:{symbol}",
                        quality=0.85 if self.demo_mode else 0.9,
                        notes=(
                            "Reference catalog only; demo authentication does not provide quote/history access."
                            if self.demo_mode else None
                        ),
                    )],
                ))
                if len(result) >= self.max_rows:
                    break
            raw_count = payload.get("count")
            try:
                count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                count = None
            if len(rows) < page_size or (count is not None and page * page_size >= count):
                break
            page += 1
        return result


class IranUniverseProvider(InstrumentUniverseProvider):
    provider_id = "iran-tsetmc-universe"

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if country and country.upper() != "IR":
            return []
        market = (exchange or "").upper() or None
        if market not in {None, "TSE", "IFB", "IFB_BASE"}:
            raise GlobalProviderError(f"unsupported Iran market {market}")
        try:
            rows = query_symbols(market=market, limit=10000)
        except SymbolUniverseUnavailable as exc:
            raise GlobalProviderError(str(exc)) from exc
        result: list[GlobalCompany] = []
        for item in rows:
            resolved_market = market or item.market
            if not resolved_market:
                continue
            result.append(GlobalCompany(
                country="IR",
                exchange=str(resolved_market),
                currency="IRR",
                ticker=item.symbol or item.code,
                name=item.name or item.symbol or item.code,
                raw_provider_fields={"iran_instrument_code": item.code},
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="instrument_reference",
                    source_id=item.code,
                    quality=1.0 if item.source == "tsetmc" else 0.8,
                    notes=f"source={item.source}",
                )],
            ))
        return result
