from pathlib import Path

def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

LSE = r'''"""Official London Stock Exchange Main Market share universe and delayed prices.

The public LSE Price Explorer renders from the exchange's own JSON component
endpoint. BIAP requests Main Market + Shares + LSE issuer rows, normalizes GBX
quotes to GBP, and uses official market capitalisation as the stage-one size
ranking metric. No vendor reference catalogue is used for market membership.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec, get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider
from .universe import _ordinary_equity_row


_PAGE_API = "https://api.londonstockexchange.com/api/v1/pages"
_REFRESH_API = "https://api.londonstockexchange.com/api/v1/components/refresh"
_EXPLORER_PATH = "live-markets/market-data-dashboard/price-explorer"
_PUBLIC_PAGE = "https://www.londonstockexchange.com/live-markets/market-data-dashboard/price-explorer?markets=MAINMARKET&categories=EQUITY&subcategories=1"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.londonstockexchange.com",
    "Referer": "https://www.londonstockexchange.com/",
}


def _num(value: object) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _valid_isin(value: object) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


def _gbp_value(value: object, currency: object) -> Optional[float]:
    number = _num(value)
    if number is None:
        return None
    unit = str(currency or "").strip().upper()
    if unit == "GBX":
        return number / 100.0
    if unit == "GBP":
        return number
    return None


def _ordinary_main_market_share(row: dict) -> bool:
    if str(row.get("category") or "").strip().upper() != "EQUITY":
        return False
    if row.get("islse") is not True:
        return False
    ticker = str(row.get("tidm") or "").strip().upper()
    isin = _valid_isin(row.get("isin"))
    currency = str(row.get("currency") or "").strip().upper()
    if not ticker or not isin or currency not in {"GBX", "GBP"}:
        return False

    description = str(row.get("description") or row.get("issuername") or ticker).strip()
    upper = f" {description.upper()} "
    # The LSE "Shares" subcategory already removes GDR/ADR lines. Keep explicit
    # guards so a future taxonomy change cannot silently admit non-ordinary lines.
    rejected = (
        " GDR ", " ADR ", " DEPOSITARY ", " PREFERENCE ", " PREFERRED ",
        " PREF ", " ZDP ", " WARRANT ", " RIGHTS ", " UNIT ", " UNITS ",
        " ETF ", " ETP ", " ETN ", " ETC ",
    )
    if any(token in upper for token in rejected):
        return False

    spec = get_exchange("GB", "LSE")
    normalized = {
        "name": description,
        "type": "Common Stock",
        "cfi_code": None,
    }
    return _ordinary_equity_row(
        country="GB",
        spec=spec,
        row=normalized,
        symbol=ticker,
        currency="GBP",
    )


class LSEOfficialClient:
    provider_id = "official-lse-main-market-price-explorer"

    def __init__(self, *, timeout: float = 60.0, page_size: int = 200) -> None:
        self.timeout = max(10.0, float(timeout))
        self.page_size = max(20, min(int(page_size), 500))
        self._component_id: Optional[str] = None
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return country.upper() == "GB" and exchange.upper() == "LSE"

    def _component(self, session: requests.Session) -> str:
        if self._component_id:
            return self._component_id
        try:
            response = session.get(
                _PAGE_API,
                params={"path": _EXPLORER_PATH, "parameters": "markets=MAINMARKET&categories=EQUITY"},
                headers=_HEADERS,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"LSE Price Explorer page request failed: {type(exc).__name__}") from exc
        components = payload.get("components") if isinstance(payload, dict) else None
        if not isinstance(components, list):
            raise GlobalProviderError("LSE Price Explorer returned no component list")
        match = next((row for row in components if isinstance(row, dict) and row.get("type") == "price-explorer"), None)
        component_id = str((match or {}).get("id") or "").strip()
        if not component_id:
            raise GlobalProviderError("LSE Price Explorer component id not found")
        self._component_id = component_id
        return component_id

    def _page(self, session: requests.Session, *, component_id: str, page: int) -> dict:
        params = (
            "markets=MAINMARKET&categories=EQUITY&subcategories=1&"
            f"showonlylse=true&page={page}&size={self.page_size}"
        )
        body = {
            "path": _EXPLORER_PATH,
            "parameters": params,
            "components": [{"componentId": component_id, "parameters": params}],
        }
        last_error: Optional[Exception] = None
        for attempt in range(4):
            try:
                response = session.post(
                    _REFRESH_API,
                    params={
                        "parameters": params,
                        "path": _EXPLORER_PATH,
                        "components": "priceexplorersearch",
                    },
                    json=body,
                    headers=_HEADERS,
                    timeout=self.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                content = payload[0].get("content") if isinstance(payload, list) and payload else None
                if not isinstance(content, list):
                    raise GlobalProviderError("LSE Price Explorer refresh returned no content")
                values = {
                    str(item.get("name")): item.get("value")
                    for item in content
                    if isinstance(item, dict) and item.get("name")
                }
                search = values.get("priceexplorersearch")
                if not isinstance(search, dict):
                    raise GlobalProviderError("LSE Price Explorer search block missing")
                return search
            except (requests.RequestException, ValueError, GlobalProviderError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        raise GlobalProviderError(
            f"LSE Price Explorer refresh failed: {type(last_error).__name__ if last_error else 'unknown'}"
        )

    def eligible_rows(self) -> tuple[list[dict], dict]:
        session = requests.Session()
        component_id = self._component(session)
        rows: list[dict] = []
        total = 0
        page = 0
        seen: set[str] = set()
        while True:
            search = self._page(session, component_id=component_id, page=page)
            try:
                total = max(total, int(search.get("totalElements") or 0))
            except (TypeError, ValueError):
                pass
            content = search.get("content")
            if not isinstance(content, list):
                raise GlobalProviderError("LSE Price Explorer page has no row list")
            for row in content:
                if not isinstance(row, dict) or not _ordinary_main_market_share(row):
                    continue
                ticker = str(row.get("tidm") or "").strip().upper()
                if ticker in seen:
                    continue
                seen.add(ticker)
                rows.append(row)
            if search.get("last") is True or not content:
                break
            try:
                total_pages = int(search.get("totalPages") or 0)
            except (TypeError, ValueError):
                total_pages = 0
            page += 1
            if (total_pages and page >= total_pages) or page > 20:
                break

        if not rows:
            raise GlobalProviderError("LSE Price Explorer returned no eligible Main Market ordinary shares")
        metadata = {
            "sourceTotal": total or len(rows),
            "officialCount": len(rows),
            "resolvedCount": len(rows),
            "resolutionCoveragePct": 100.0,
            "excludedNonOrdinaryOrNonGBP": max(0, (total or len(rows)) - len(rows)),
            "identitySource": "London Stock Exchange official Price Explorer Main Market Shares",
            "componentId": component_id,
        }
        self.last_metadata = metadata
        return rows, metadata

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        rows, _ = self.eligible_rows()
        by_ticker = {
            str(row.get("tidm") or "").strip().upper(): row
            for row in rows
            if str(row.get("tidm") or "").strip()
        }
        observed = datetime.now(timezone.utc).isoformat()
        quotes: list[dict] = []
        for company in instruments:
            row = by_ticker.get(company.ticker.strip().upper())
            if row is None:
                continue
            row_isin = _valid_isin(row.get("isin"))
            if company.isin and row_isin and company.isin.upper() != row_isin:
                continue
            price = _gbp_value(row.get("lastprice") or row.get("midPrice"), row.get("currency"))
            if price is None or price <= 0:
                continue
            high = _gbp_value(row.get("fiftyTwoWeeksMax"), row.get("currency"))
            low = _gbp_value(row.get("fiftyTwoWeeksMin"), row.get("currency"))
            range_position = None
            if high is not None and low is not None and high > low:
                range_position = max(0.0, min(1.0, (price - low) / (high - low)))
            market_cap = max(0.0, float(_num(row.get("marketcapitalization")) or 0.0))
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": price,
                "averageVolume": 0.0,
                "liquidityValue": market_cap,
                "rangePosition": range_position,
                "quoteDate": observed,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "sourceUrl": _PUBLIC_PAGE,
                "isin": row_isin,
                "marketCapGBP": market_cap or None,
                "screeningMetric": "official_lse_market_cap_gbp",
                "originalQuoteCurrency": str(row.get("currency") or "").upper(),
            })
        errors: list[str] = []
        if not quotes:
            errors.append("LSE official Price Explorer returned no usable Main Market prices")
        return quotes, errors, "London Stock Exchange official Price Explorer Main Market Shares"


class LSEMainMarketUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-lse-main-market-shares"

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.client = LSEOfficialClient(timeout=timeout)
        self.last_metadata: dict = {}

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.client.supported(country, exchange):
            raise GlobalProviderError(f"LSE official universe is not configured for {country}/{exchange}")
        spec = get_exchange(country, exchange)
        rows, metadata = self.client.eligible_rows()
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            ticker = str(row.get("tidm") or "").strip().upper()
            isin = _valid_isin(row.get("isin"))
            if not ticker or not isin:
                continue
            original_currency = str(row.get("currency") or "").strip().upper()
            result.append(GlobalCompany(
                country="GB",
                exchange=spec.code,
                currency="GBP",
                ticker=ticker,
                name=str(row.get("issuername") or row.get("description") or ticker).strip(),
                mic_code=spec.mic,
                isin=isin,
                instrument_type="Common Stock",
                market_cap=max(0.0, float(_num(row.get("marketcapitalization")) or 0.0)) or None,
                raw_provider_fields={
                    "official_universe": True,
                    "lse_market": "MAINMARKET",
                    "lse_category": row.get("category"),
                    "lse_subcategory": "Shares",
                    "lse_issuer_code": row.get("issuercode"),
                    "lse_original_currency": original_currency,
                    "lse_description": row.get("description"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"LSE:MAINMARKET:{ticker}:{isin}",
                    source_url=_PUBLIC_PAGE,
                    observed_at=observed,
                    quality=1.0,
                    notes="London Stock Exchange official Price Explorer; Main Market Shares, LSE issuers; GBX normalized to GBP.",
                )],
            ))
        if not result:
            raise GlobalProviderError("LSE official universe normalized no eligible shares")
        self.last_metadata = dict(metadata)
        self.last_metadata["officialCount"] = len(result)
        self.last_metadata["resolvedCount"] = len(result)
        self.last_metadata["resolutionCoveragePct"] = 100.0
        return result
'''

TEST = r'''from __future__ import annotations

from global_markets.country_packs import get_exchange
from global_markets.lse_official import (
    LSEMainMarketUniverseProvider,
    LSEOfficialClient,
    _gbp_value,
    _ordinary_main_market_share,
)


def _row(tidm="TEST", isin="GB00TEST00001", currency="GBX", description="TEST PLC ORD 1P", price=250.0, market_cap=1_000_000_000):
    return {
        "category": "EQUITY",
        "currency": currency,
        "description": description,
        "isin": isin,
        "islse": True,
        "issuername": "TEST PLC",
        "lastprice": price,
        "marketcapitalization": market_cap,
        "fiftyTwoWeeksMax": 300.0,
        "fiftyTwoWeeksMin": 200.0,
        "tidm": tidm,
    }


def test_gbx_is_normalized_to_gbp():
    assert _gbp_value(250, "GBX") == 2.5
    assert _gbp_value(2.5, "GBP") == 2.5
    assert _gbp_value(2.5, "USD") is None


def test_lse_filter_keeps_ordinary_share_and_rejects_nonordinary():
    assert _ordinary_main_market_share(_row()) is True
    assert _ordinary_main_market_share(_row(description="TEST PLC GDR (REG S)")) is False
    assert _ordinary_main_market_share(_row(description="TEST PLC 8% PREFERENCE")) is False
    assert _ordinary_main_market_share(_row(currency="USD")) is False
    assert _ordinary_main_market_share(_row(tidm="1ABC")) is False


def test_lse_universe_uses_official_identity_and_gbp(monkeypatch):
    provider = LSEMainMarketUniverseProvider()
    rows = [_row(tidm="ABC", isin="GB0000000001")]
    monkeypatch.setattr(provider.client, "eligible_rows", lambda: (rows, {"officialCount": 1}))
    result = list(provider.list_instruments(country="GB", exchange="LSE"))
    assert len(result) == 1
    company = result[0]
    assert company.ticker == "ABC"
    assert company.currency == "GBP"
    assert company.isin == "GB0000000001"
    assert company.sources[0].provider == "official-lse-main-market-shares"


def test_lse_quotes_join_by_ticker_and_convert_price(monkeypatch):
    client = LSEOfficialClient()
    rows = [_row(tidm="ABC", isin="GB0000000001", price=250.0, market_cap=2_000_000_000)]
    monkeypatch.setattr(client, "eligible_rows", lambda: (rows, {"officialCount": 1}))
    company = list(LSEMainMarketUniverseProvider().list_instruments(country="GB", exchange="LSE")) if False else None
    from global_markets.models import GlobalCompany
    instrument = GlobalCompany(
        country="GB", exchange="LSE", mic_code="XLON", currency="GBP",
        ticker="ABC", name="ABC PLC", isin="GB0000000001",
    )
    quotes, errors, source = client.batch_quotes([instrument], "GB", get_exchange("GB", "LSE"))
    assert errors == []
    assert len(quotes) == 1
    assert quotes[0]["price"] == 2.5
    assert quotes[0]["liquidityValue"] == 2_000_000_000
    assert quotes[0]["provider"] == "official-lse-main-market-price-explorer"
    assert "London Stock Exchange" in source
'''

Path("analysis/global_markets/lse_official.py").write_text(LSE, encoding="utf-8")
Path("analysis/tests/test_global_lse_official.py").write_text(TEST, encoding="utf-8")

replace_once(
    "analysis/global_markets/runtime.py",
    "from .kap_current import KAPCurrentFundamentalsProvider\n",
    "from .kap_current import KAPCurrentFundamentalsProvider\nfrom .lse_official import LSEMainMarketUniverseProvider\n",
)
replace_once(
    "analysis/global_markets/runtime.py",
    '''    registry.register_universe("IE", "EURONEXT_DUBLIN", dublin_universe)\n\n''',
    '''    registry.register_universe("IE", "EURONEXT_DUBLIN", dublin_universe)\n\n    lse_universe = PersistentUniverseProvider(\n        LSEMainMarketUniverseProvider(),\n        fresh_hours=12,\n    )\n    registry.register_universe("GB", "LSE", lse_universe)\n\n''',
)

replace_once(
    "analysis/global_markets/scanner.py",
    "from .models import GlobalCompany, SourceEvidence\n",
    "from .models import GlobalCompany, SourceEvidence\nfrom .lse_official import LSEOfficialClient\n",
)
replace_once(
    "analysis/global_markets/scanner.py",
    "        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))\n",
    "        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))\n        self.lse_official = LSEOfficialClient(timeout=max(45.0, self.timeout))\n",
)
replace_once(
    "analysis/global_markets/scanner.py",
    "            self.euronext_live.supported(country.upper(), spec.code)\n",
    "            self.euronext_live.supported(country.upper(), spec.code)\n            or self.lse_official.supported(country.upper(), spec.code)\n",
)
replace_once(
    "analysis/global_markets/scanner.py",
    '''        if self.nasdaq_nordic.supported(country.upper(), spec.code):\n            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)\n''',
    '''        if self.lse_official.supported(country.upper(), spec.code):\n            quotes, screening_errors, market_source = self.lse_official.batch_quotes(selected_universe, country.upper(), spec)\n        elif self.nasdaq_nordic.supported(country.upper(), spec.code):\n            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)\n''',
)
