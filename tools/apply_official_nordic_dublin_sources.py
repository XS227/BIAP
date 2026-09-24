from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:220]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


NASDAQ = r'''"""Official Nasdaq Nordic Main Market universe and stage-one quotes.

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
'''

Path("analysis/global_markets/nasdaq_nordic.py").write_text(NASDAQ, encoding="utf-8")

# Euronext Dublin: use the full official regulated-stocks CSV because the
# filtered XMSM gateway intermittently returns 500. Exact Market membership is
# then selected from the official CSV, not inferred from issuer domicile.
p = Path("analysis/global_markets/euronext_live.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "from .models import GlobalCompany\nfrom .providers import GlobalProviderError\n",
    "from .models import GlobalCompany, SourceEvidence\nfrom .providers import GlobalProviderError, InstrumentUniverseProvider\n",
    1,
)
anchor = '''_MARKETS: dict[tuple[str, str], str] = {
'''
if "_EXACT_MARKET_NAMES" not in text:
    idx = text.index("}\n\n\ndef _float", text.index(anchor))
    insert = '''\n\n_EXACT_MARKET_NAMES: dict[tuple[str, str], str] = {
    ("IE", "EURONEXT_DUBLIN"): "Euronext Dublin",
}
'''
    text = text[:idx+2] + insert + text[idx+2:]

old = '''            response = requests.get(
                _DOWNLOAD,
                params={"mics": mic},
                headers=headers,
                timeout=self.timeout,
            )
'''
new = '''            # Dublin's XMSM-filtered download gateway is intermittently broken
            # upstream. The unfiltered regulated-stocks CSV is healthy and carries
            # an exact Market column, so Dublin is selected from that authoritative
            # full file instead of falling back to a vendor catalog.
            params = None if (country.upper(), exchange.upper()) == ("IE", "EURONEXT_DUBLIN") else {"mics": mic}
            response = requests.get(
                _DOWNLOAD,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
'''
if new not in text:
    if old not in text:
        raise SystemExit("euronext request anchor missing")
    text = text.replace(old, new, 1)

old = '''        if not rows:
            raise GlobalProviderError(f"Euronext regulated directory returned no usable rows for {country}/{exchange}")
        return mic, rows
'''
new = '''        exact_market = _EXACT_MARKET_NAMES.get((country.upper(), exchange.upper()))
        if exact_market:
            rows = [row for row in rows if str(row.get("market") or "").strip() == exact_market]
        if not rows:
            raise GlobalProviderError(f"Euronext regulated directory returned no usable rows for {country}/{exchange}")
        return mic, rows
'''
if new not in text:
    if old not in text:
        raise SystemExit("euronext rows anchor missing")
    text = text.replace(old, new, 1)

if "class EuronextRegulatedUniverseProvider" not in text:
    text += r'''

class EuronextRegulatedUniverseProvider(InstrumentUniverseProvider):
    """Authoritative regulated-stock membership for Euronext Dublin."""

    provider_id = "official-euronext-regulated-universe"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.client = EuronextLiveRegulatedClient(timeout=timeout)
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("IE", "EURONEXT_DUBLIN")

    def list_instruments(self, *, country=None, exchange=None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"Euronext regulated universe is not configured for {country}/{exchange}")
        country = country.upper()
        exchange = exchange.upper()
        mic, rows = self.client._download(country=country, exchange=exchange)
        observed = datetime.now().astimezone().isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            isin = _valid_isin(row.get("isin"))
            ticker = str(row.get("symbol") or "").strip().upper()
            currency = str(row.get("currency") or "").strip().upper()
            if not isin or not ticker or not currency:
                continue
            result.append(GlobalCompany(
                country=country,
                exchange=exchange,
                currency=currency,
                ticker=ticker,
                name=str(row.get("name") or ticker).strip(),
                mic_code=mic,
                isin=isin,
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "euronext_market": row.get("market"),
                    "euronext_regulated_directory": True,
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"EURONEXT:{isin}:{mic}",
                    source_url=_DOWNLOAD,
                    observed_at=observed,
                    quality=1.0,
                    notes="Exact Euronext Dublin regulated-stock directory membership.",
                )],
            ))
        if not result:
            raise GlobalProviderError("Euronext Dublin official universe normalized no instruments")
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "nativeMic": mic,
            "identitySource": "Euronext regulated stocks official CSV",
        }
        return result
'''
p.write_text(text, encoding="utf-8")

# Runtime: FIRDS remains for continental Euronext/Oslo/Madrid. Nasdaq itself
# becomes authoritative for all four Nordic Main Markets; Euronext itself for Dublin.
p = Path("analysis/global_markets/runtime.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "from .esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider\n",
    "from .esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider\nfrom .euronext_live import EuronextRegulatedUniverseProvider\nfrom .nasdaq_nordic import NasdaqNordicUniverseProvider\n",
    1,
)
old = '''    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)
    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)
    registry.register_universe("NL", "EURONEXT_AMSTERDAM", firds_eu)
    registry.register_universe("BE", "EURONEXT_BRUSSELS", firds_eu)
    registry.register_universe("PT", "EURONEXT_LISBON", firds_eu)
    registry.register_universe("NO", "EURONEXT_OSLO", firds_eu)
    registry.register_universe("ES", "BME_MADRID", firds_eu)
    registry.register_universe("SE", "NASDAQ_STOCKHOLM", firds_eu)
    registry.register_universe("DK", "NASDAQ_COPENHAGEN", firds_eu)

'''
new = '''    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)
    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)
    registry.register_universe("NL", "EURONEXT_AMSTERDAM", firds_eu)
    registry.register_universe("BE", "EURONEXT_BRUSSELS", firds_eu)
    registry.register_universe("PT", "EURONEXT_LISBON", firds_eu)
    registry.register_universe("NO", "EURONEXT_OSLO", firds_eu)
    registry.register_universe("ES", "BME_MADRID", firds_eu)

    nasdaq_nordic = PersistentUniverseProvider(
        NasdaqNordicUniverseProvider(),
        fresh_hours=12,
    )
    for country, exchange in (
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ):
        registry.register_universe(country, exchange, nasdaq_nordic)

    dublin_universe = PersistentUniverseProvider(
        EuronextRegulatedUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("IE", "EURONEXT_DUBLIN", dublin_universe)

'''
if new not in text:
    if old not in text:
        raise SystemExit("runtime registration anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Scanner: exchange-native official full-market sources take precedence over
# paid generic feeds for their own venues.
p = Path("analysis/global_markets/scanner.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "from .models import GlobalCompany\n",
    "from .models import GlobalCompany\nfrom .nasdaq_nordic import NasdaqNordicOfficialClient\n",
    1,
)
text = text.replace(
    "        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))\n",
    "        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))\n        self.nasdaq_nordic = NasdaqNordicOfficialClient(timeout=max(20.0, self.timeout))\n",
    1,
)
old = '''        if not self.market_api_key and self.eodhd_bulk is None and not self.euronext_live.supported(country.upper(), spec.code):
'''
new = '''        official_market_source = (
            self.euronext_live.supported(country.upper(), spec.code)
            or self.nasdaq_nordic.supported(country.upper(), spec.code)
        )
        if not self.market_api_key and self.eodhd_bulk is None and not official_market_source:
'''
if new not in text:
    if old not in text:
        raise SystemExit("scanner fallback anchor missing")
    text = text.replace(old, new, 1)
old = '''        if self.euronext_live.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.euronext_live.batch_quotes(selected_universe, country.upper(), spec)
        elif self.eodhd_bulk is not None:
'''
new = '''        if self.nasdaq_nordic.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)
        elif self.euronext_live.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.euronext_live.batch_quotes(selected_universe, country.upper(), spec)
        elif self.eodhd_bulk is not None:
'''
if new not in text:
    if old not in text:
        raise SystemExit("scanner quote source anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Dublin official regulated list includes a GBP-traded listing in the current
# directory; currency must not invalidate authoritative membership in cache.
replace_once(
    "analysis/global_markets/country_packs.py",
    'E("EURONEXT_DUBLIN", "Euronext Dublin", ("EUR",), "XDUB", ("XMSM", "XESM")),',
    'E("EURONEXT_DUBLIN", "Euronext Dublin", ("EUR", "GBP"), "XDUB", ("XMSM", "XESM")),',
)

# Invalidate all pre-Nasdaq-official Nordic and pre-Euronext-official Dublin snapshots.
replace_once(
    "analysis/global_markets/cached_universe.py",
    "# Version 12 extends authoritative FIRDS membership to Sweden and Denmark.\n# Old vendor/reference snapshots for XSTO/XCSE must not survive this semantic\n# change; all authoritative market caches are rebuilt under the same schema.\nCACHE_SCHEMA_VERSION = 12\n",
    "# Version 13 replaces incomplete FIRDS Nordic membership with Nasdaq's own\n# Main Market screener for STO/CPH/HEL/ICE and wires Euronext's official Dublin\n# regulated-stock directory. Older snapshots must not survive this source change.\nCACHE_SCHEMA_VERSION = 13\n",
)
replace_once(
    "analysis/tests/test_global_universe_cache_schema.py",
    "def test_global_universe_cache_schema_is_firds_nordics_v12():\n    assert CACHE_SCHEMA_VERSION == 12\n",
    "def test_global_universe_cache_schema_is_official_nordic_dublin_v13():\n    assert CACHE_SCHEMA_VERSION == 13\n",
)

# Existing SE/DK regression now asserts the stronger official Nasdaq source.
Path("analysis/tests/test_global_firds_se_dk.py").write_text(r'''from global_markets.nasdaq_nordic import NasdaqNordicUniverseProvider
from global_markets.runtime import build_registry


def test_nasdaq_official_supports_all_nordic_main_markets():
    provider = NasdaqNordicUniverseProvider()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ]:
        assert provider.supported(country, exchange)


def test_runtime_uses_authoritative_nasdaq_for_nordic_main_markets():
    registry = build_registry()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ]:
        wrapper = registry.universe(country, exchange)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == "official-nasdaq-nordic-main-market"
''', encoding="utf-8")

Path("analysis/tests/test_global_official_nordic_dublin.py").write_text(r'''from global_markets.euronext_live import EuronextRegulatedUniverseProvider
from global_markets.nasdaq_nordic import (
    NasdaqNordicOfficialClient,
    NasdaqNordicUniverseProvider,
    _ordinary_share_row,
    normalize_nordic_symbol,
)
from global_markets.country_packs import get_exchange
from global_markets.runtime import build_registry


def test_nordic_symbol_normalization_matches_existing_history_convention():
    assert normalize_nordic_symbol("VOLV B") == "VOLV.B"
    assert normalize_nordic_symbol("MAERSK A") == "MAERSK.A"
    assert normalize_nordic_symbol("NOKIA") == "NOKIA"


def test_nordic_ordinary_filter_rejects_depositary_receipts():
    spec = get_exchange("FI", "NASDAQ_HELSINKI")
    common = {"assetClass": "SHARES", "isin": "FI0009000681", "symbol": "NOKIA", "currency": "EUR", "fullName": "Nokia Oyj"}
    fdr = {"assetClass": "SHARES", "isin": "FI4000349378", "symbol": "TALLINK", "currency": "EUR", "fullName": "AS Tallink Grupp FDR"}
    assert _ordinary_share_row(common, spec)
    assert not _ordinary_share_row(fdr, spec)


def test_official_market_codes_are_exact():
    assert NasdaqNordicOfficialClient.market_code("SE", "NASDAQ_STOCKHOLM") == "STO"
    assert NasdaqNordicOfficialClient.market_code("DK", "NASDAQ_COPENHAGEN") == "CPH"
    assert NasdaqNordicOfficialClient.market_code("FI", "NASDAQ_HELSINKI") == "HEL"
    assert NasdaqNordicOfficialClient.market_code("IS", "NASDAQ_ICELAND") == "ICE"


def test_registry_wires_dublin_and_all_nordics_to_official_sources():
    registry = build_registry()
    expected = {
        ("SE", "NASDAQ_STOCKHOLM"): "official-nasdaq-nordic-main-market",
        ("DK", "NASDAQ_COPENHAGEN"): "official-nasdaq-nordic-main-market",
        ("FI", "NASDAQ_HELSINKI"): "official-nasdaq-nordic-main-market",
        ("IS", "NASDAQ_ICELAND"): "official-nasdaq-nordic-main-market",
        ("IE", "EURONEXT_DUBLIN"): "official-euronext-regulated-universe",
    }
    for key, provider_id in expected.items():
        wrapper = registry.universe(*key)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == provider_id


def test_dublin_provider_support_scope_is_explicit():
    provider = EuronextRegulatedUniverseProvider()
    assert provider.supported("IE", "EURONEXT_DUBLIN")
    assert not provider.supported("FR", "EURONEXT_PARIS")
''', encoding="utf-8")
