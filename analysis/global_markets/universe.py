"""Instrument universe adapters for BIAP Global country/exchange selection.

Reference-data discovery is intentionally separable from price/history access.
Twelve Data documents a public ``demo`` key for the /stocks catalog. BIAP may
use that catalog when no private market-data credential is configured, but the
result is tagged as reference-only evidence and is never treated as a price
feed or sufficient evidence for a BUY recommendation.
"""

from __future__ import annotations

import os
import re
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
    if cfi and not cfi.startswith("E"):
        return False

    allowed_currencies = {value.upper() for value in spec.currencies}
    if country.upper() == "GB":
        allowed_currencies.add("GBX")
    if allowed_currencies and currency.upper() not in allowed_currencies:
        return False

    ticker = symbol.strip().upper()
    if not ticker:
        return False
    if ".PR." in ticker or ticker.endswith(".PR") or ".RT." in ticker or ticker.endswith(".RT"):
        return False

    if country.upper() == "GB" and ticker[0].isdigit():
        return False

    name = f" {str(row.get('name') or '').upper()} "
    rejected_name_tokens = (
        " FRN ", " FLOATING RATE ", " BOND ", " NOTE ", " NOTES ",
        " WARRANT ", " WARRANTS ", " RIGHTS ", " CERTIFICATE ",
        " PREFERENCE ", " PREFERRED ", " CONVERTIBLE BOND ",
        " ETN ", " ETC ", " STRUCTURED ", " ZERO COUPON ",
        " MEDIUM TERM ", " DEBT SECURITY ", " UNITS ", " UNIT ",
        " SPAC ",
    )
    if any(token in name for token in rejected_name_tokens):
        return False

    # Leveraged/inverse exchange products and certificates can be mislabeled by
    # reference vendors as Common Stock. They are not operating-company shares
    # and must never enter Kiasha's equity universe.
    structured_markers = (
        " MINI FUTURE ", " TURBO ", " LEVERAGED ", " INVERSE ",
        " TRACKER ", " CERTIFICATE ", " OPEN END ",
    )
    if any(marker in name for marker in structured_markers):
        return False
    stripped_name = name.strip()
    if stripped_name.startswith(("BULL ", "BEAR ")):
        return False
    if re.search(r"\bX[2-9]\b", stripped_name) and any(token in stripped_name for token in ("BULL", "BEAR", "LONG", "SHORT")):
        return False

    # US reference catalogs frequently expose blank-check/SPAC shells as
    # "Common Stock". They are legal equities but are not operating-company
    # shares and routinely lack the fundamental history Kiasha is meant to
    # compare. Keep de-SPAC operating companies (whose current legal name no
    # longer contains an acquisition-shell marker) while excluding active shells.
    if country.upper() == "US":
        acquisition_shell_markers = (
            " ACQUISITION CORP ", " ACQUISITION CORP. ",
            " ACQUISITION CORPORATION ", " ACQUISITION COMPANY ",
            " ACQUISITION CO ", " ACQUISITION CO. ",
            " ACQUISITION INC ", " ACQUISITION INC. ",
            " ACQUISITION LTD ", " ACQUISITION LTD. ",
            " ACQUISITION LIMITED ", " BLANK CHECK ",
        )
        if any(marker in name for marker in acquisition_shell_markers):
            return False

    return True


class TwelveDataUniverseProvider(InstrumentUniverseProvider):
    provider_id = "twelve-data-universe"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 15.0, max_rows: Optional[int] = None) -> None:
        configured_key = api_key if api_key is not None else os.environ.get("BIAP_GLOBAL_MARKET_API_KEY")
        self.api_key = (configured_key or "demo").strip()
        self.demo_mode = self.api_key.lower() == "demo"
        if self.demo_mode:
            self.provider_id = "twelve-data-universe-demo"
        self.base_url = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")
        self.timeout = max(3.0, float(timeout))
        configured_max = max_rows if max_rows is not None else int(os.environ.get("BIAP_GLOBAL_UNIVERSE_MAX_ROWS", "20000"))
        self.max_rows = max(1, min(int(configured_max), 20000))

    def _request(self, params: dict, *, endpoint: str = "stocks") -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/{endpoint.lstrip('/')}", params={**params, "apikey": self.api_key})
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

    def _company_from_row(self, *, country: str, spec: ExchangeSpec, row: dict) -> Optional[GlobalCompany]:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            return None
        returned_mic = str(row.get("mic_code") or "").strip().upper() or None
        accepted_mics = set(spec.accepted_mics)
        if accepted_mics and returned_mic and returned_mic not in accepted_mics:
            return None
        currency = str(row.get("currency") or (spec.currencies[0] if spec.currencies else "")).strip().upper()
        if not currency:
            return None

        normalized = dict(row)
        if not normalized.get("name") and normalized.get("instrument_name"):
            normalized["name"] = normalized.get("instrument_name")
        if not normalized.get("type") and normalized.get("instrument_type"):
            normalized["type"] = normalized.get("instrument_type")
        if not _ordinary_equity_row(country=country, spec=spec, row=normalized, symbol=symbol, currency=currency):
            return None

        instrument_type = str(normalized.get("type") or "Common Stock").strip()
        return GlobalCompany(
            country=country.upper(),
            exchange=spec.code,
            mic_code=returned_mic or spec.mic,
            currency=currency,
            ticker=symbol,
            name=str(normalized.get("name") or symbol).strip(),
            isin=_clean_isin(normalized.get("isin")),
            instrument_type=instrument_type or "Common Stock",
            raw_provider_fields={
                "figi": str(normalized.get("figi_code") or "").strip() or None,
                "cfi": str(normalized.get("cfi_code") or "").strip() or None,
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
        )

    def search_instruments(
        self,
        *,
        country: str,
        exchange: str,
        query: str,
        limit: int = 120,
    ) -> list[GlobalCompany]:
        """Resolve a ticker or company name without relying on a cached prefix.

        Exact ``/stocks?symbol=...`` lookup is attempted first because it is the
        most reliable recovery path for a ticker such as AAPL when a persistent
        exchange snapshot is stale or incomplete. ``symbol_search`` is then
        merged for company-name/prefix discovery. Every returned row is still
        constrained to the selected venue and ordinary equities.
        """
        text = str(query or "").strip()
        if not text:
            return []
        spec = get_exchange(country, exchange)
        requested = max(1, min(int(limit), 120))
        payloads: list[dict] = []

        # Do not force the primary MIC here: NASDAQ symbols can be reported on
        # segment MICs such as XNGS/XNMS. _company_from_row validates all of the
        # exchange's accepted MICs after retrieval.
        try:
            payloads.append(self._request(
                {"symbol": text, "outputsize": requested, "format": "JSON", "type": "Common Stock"},
                endpoint="stocks",
            ))
        except GlobalProviderError:
            pass

        try:
            payloads.append(self._request(
                {"symbol": text, "outputsize": requested, "show_plan": "false"},
                endpoint="symbol_search",
            ))
        except GlobalProviderError:
            pass

        result: list[GlobalCompany] = []
        seen: set[tuple[str, str]] = set()
        for payload in payloads:
            rows = payload.get("data")
            if not isinstance(rows, list):
                continue
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                row = dict(raw)
                row.setdefault("name", raw.get("instrument_name"))
                row.setdefault("type", raw.get("instrument_type"))
                item = self._company_from_row(country=country, spec=spec, row=row)
                if item is None:
                    continue
                key = ((item.mic_code or item.exchange).upper(), item.ticker.upper())
                if key in seen:
                    continue
                seen.add(key)
                result.append(item)
                if len(result) >= requested:
                    return result
        return result

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if not country or not exchange:
            raise GlobalProviderError("country and exchange are required for bounded instrument discovery")
        spec = get_exchange(country, exchange)
        result: list[GlobalCompany] = []
        seen: set[tuple[str, str]] = set()
        seen_pages: set[tuple[str, ...]] = set()
        page = 1
        # Large pages keep refresh cost bounded when the provider honors the
        # requested size. Some catalog tiers cap each response below this value;
        # in that case BIAP keeps requesting subsequent pages instead of
        # mistaking the page-local `count` for a universe total.
        page_size = min(1000, self.max_rows)
        raw_rows_seen = 0
        max_pages = min(500, max(3, self.max_rows + 2))

        while raw_rows_seen < self.max_rows and page <= max_pages:
            payload = self._get_page(country=country, spec=spec, page=page, outputsize=page_size)
            rows = payload.get("data")
            if not isinstance(rows, list) or not rows:
                break

            signature = tuple(str(row.get("symbol") or "").strip().upper() for row in rows if isinstance(row, dict))
            if signature and signature in seen_pages:
                # Defensive guard for providers/tiers that ignore the page
                # parameter and repeatedly return page one.
                break
            if signature:
                seen_pages.add(signature)

            raw_rows_seen += len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = self._company_from_row(country=country, spec=spec, row=row)
                if item is None:
                    continue
                venue_key = (item.mic_code or spec.mic or spec.code).upper()
                dedupe_key = (venue_key, item.ticker.upper())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                result.append(item)
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
