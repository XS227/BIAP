"""Instrument universe adapters for BIAP Global country/exchange selection."""

from __future__ import annotations

import os
from typing import Iterable, Optional

import httpx

from symbol_universe import SymbolUniverseUnavailable, query_symbols

from .country_packs import ExchangeSpec, get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


class TwelveDataUniverseProvider(InstrumentUniverseProvider):
    provider_id = "twelve-data-universe"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 15.0, max_rows: int = 5000) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.base_url = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")
        self.timeout = max(3.0, float(timeout))
        self.max_rows = max(1, min(int(max_rows), 20000))
        if not self.api_key:
            raise GlobalProviderError("BIAP_GLOBAL_MARKET_API_KEY is required for global instrument discovery")

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

    def _get_page(self, *, country: str, spec: ExchangeSpec, page: int, outputsize: int) -> dict:
        base = {"country": country.upper(), "page": page, "outputsize": outputsize, "format": "JSON", "type": "Common Stock"}
        if spec.mic:
            first = self._request({**base, "mic_code": spec.mic})
            if isinstance(first.get("data"), list) and first.get("data"):
                return first
            # Some vendors catalog segment MICs while our selector stores the
            # operating MIC. Retry with the human exchange label, then validate
            # each returned MIC against accepted operating/segment aliases.
            if spec.mic_aliases:
                return self._request({**base, "exchange": spec.label})
            return first
        return self._request({**base, "exchange": spec.label})

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if not country or not exchange:
            raise GlobalProviderError("country and exchange are required for bounded instrument discovery")
        spec = get_exchange(country, exchange)
        accepted_mics = set(spec.accepted_mics)
        result: list[GlobalCompany] = []
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
                currency = str(row.get("currency") or (spec.currencies[0] if spec.currencies else "")).strip().upper()
                if not currency:
                    continue
                instrument_type = str(row.get("type") or "Common Stock").strip()
                if "stock" not in instrument_type.lower() and "equity" not in instrument_type.lower():
                    continue
                result.append(GlobalCompany(
                    country=country.upper(),
                    exchange=spec.code,
                    mic_code=returned_mic or spec.mic,
                    currency=currency,
                    ticker=symbol,
                    name=str(row.get("name") or symbol).strip(),
                    isin=str(row.get("isin") or "").strip().upper() or None,
                    instrument_type=instrument_type or "Common Stock",
                    raw_provider_fields={
                        "figi": str(row.get("figi_code") or "").strip() or None,
                        "cfi": str(row.get("cfi_code") or "").strip() or None,
                    },
                    sources=[SourceEvidence(
                        provider=self.provider_id,
                        source_type="instrument_reference",
                        source_id=f"{country.upper()}:{returned_mic or spec.mic or spec.code}:{symbol}",
                        quality=0.9,
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
