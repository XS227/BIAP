from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:240]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


EURONEXT = r'''"""Official Euronext regulated-equity directory and EOD snapshot.

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
'''

Path("analysis/global_markets/euronext_live.py").write_text(EURONEXT, encoding="utf-8")

# FIRDS: official Euronext directory first, OpenFIGI only for exact FIRDS ISINs
# missing from that official venue directory.
p = Path("analysis/global_markets/esma_firds_universe.py")
text = p.read_text(encoding="utf-8")
old = "from .country_packs import ExchangeSpec, get_exchange\n"
new = old + "from .euronext_live import EuronextLiveRegulatedClient\n"
if new not in text:
    if old not in text: raise SystemExit("FIRDS import anchor missing")
    text = text.replace(old, new, 1)
old = "        self.last_metadata: dict = {}\n"
new = old + "        self.euronext_directory = EuronextLiveRegulatedClient(timeout=self.timeout)\n"
if new not in text:
    if old not in text: raise SystemExit("FIRDS init anchor missing")
    text = text.replace(old, new, 1)

# Rename original OpenFIGI-only implementation.
old_sig = "    def _resolve(self, identities: list[dict], *, native_mic: str) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]]]:\n"
new_sig = "    def _resolve_openfigi(self, identities: list[dict], *, native_mic: str) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]]]:\n"
if new_sig not in text:
    if old_sig not in text: raise SystemExit("FIRDS resolve signature anchor missing")
    text = text.replace(old_sig, new_sig, 1)

anchor = "        return resolved, missing, ambiguous\n\n    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):\n"
replacement = '''        return resolved, missing, ambiguous\n\n    def _resolve(self, identities: list[dict], *, country: str, exchange: str, native_mic: str) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]], dict]:\n        resolved: dict[str, dict] = {}\n        missing: dict[str, str] = {}\n        ambiguous: dict[str, list[str]] = {}\n        metadata: dict = {"directoryMatched": 0, "openfigiMatched": 0}\n\n        unresolved_identities = identities\n        if self.euronext_directory.supported(country, exchange):\n            try:\n                directory_resolved, directory_metadata = self.euronext_directory.resolve_isins(\n                    identities, country=country, exchange=exchange\n                )\n                resolved.update(directory_resolved)\n                metadata.update(directory_metadata)\n                metadata["directoryMatched"] = len(directory_resolved)\n                unresolved_identities = [\n                    row for row in identities if str(row.get("isin") or "").upper() not in resolved\n                ]\n            except GlobalProviderError as exc:\n                metadata["directoryError"] = str(exc)[:260]\n\n        if unresolved_identities:\n            figi_resolved, missing, figi_ambiguous = self._resolve_openfigi(\n                unresolved_identities, native_mic=native_mic\n            )\n            for mapping in figi_resolved.values():\n                mapping["resolver"] = "openfigi-ticker-resolver"\n            resolved.update(figi_resolved)\n            ambiguous.update(figi_ambiguous)\n            metadata["openfigiMatched"] = len(figi_resolved)\n        return resolved, missing, ambiguous, metadata\n\n    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):\n'''
if replacement not in text:
    if anchor not in text: raise SystemExit("FIRDS resolve/list anchor missing")
    text = text.replace(anchor, replacement, 1)

old = "        resolved, missing, ambiguous = self._resolve(identities, native_mic=native_mic)\n"
new = "        resolved, missing, ambiguous, resolver_metadata = self._resolve(identities, country=country, exchange=exchange, native_mic=native_mic)\n"
if new not in text:
    if old not in text: raise SystemExit("FIRDS resolve call anchor missing")
    text = text.replace(old, new, 1)

old = '''            "identitySource": "ESMA FIRDS FULINS equity full files",\n            "tickerResolver": "OpenFIGI",\n            "missingResolverCount": len(missing),\n'''
new = '''            "identitySource": "ESMA FIRDS FULINS equity full files",\n            "tickerResolver": "Euronext Live regulated directory + OpenFIGI fallback" if self.euronext_directory.supported(country, exchange) else "OpenFIGI",\n            **resolver_metadata,\n            "missingResolverCount": len(missing),\n'''
if new not in text:
    if old not in text: raise SystemExit("FIRDS metadata anchor missing")
    text = text.replace(old, new, 1)

# Replace static OpenFIGI resolver evidence with dynamic official-directory vs fallback evidence.
old = '''                    SourceEvidence(\n                        provider="openfigi-ticker-resolver",\n                        source_type="instrument_identifier_mapping",\n                        source_id=str(mapping.get("figi") or isin),\n                        source_url="https://api.openfigi.com/v3/mapping",\n                        observed_at=observed,\n                        quality=0.9,\n                        notes="Ticker resolution only; does not determine market membership.",\n                    ),\n'''
new = '''                    SourceEvidence(\n                        provider=str(mapping.get("resolver") or "openfigi-ticker-resolver"),\n                        source_type="instrument_identifier_mapping",\n                        source_id=str(mapping.get("figi") or isin),\n                        source_url=(\n                            "https://live.euronext.com/en/products/equities/regulated/list"\n                            if mapping.get("resolver") == "official-euronext-live-regulated"\n                            else "https://api.openfigi.com/v3/mapping"\n                        ),\n                        observed_at=observed,\n                        quality=1.0 if mapping.get("resolver") == "official-euronext-live-regulated" else 0.9,\n                        notes=(\n                            "Official Euronext regulated-directory ISIN-to-symbol mapping; market membership remains defined by FIRDS."\n                            if mapping.get("resolver") == "official-euronext-live-regulated"\n                            else "Ticker resolution only; does not determine market membership."\n                        ),\n                    ),\n'''
if new not in text:
    if old not in text: raise SystemExit("FIRDS evidence anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Scanner: Euronext official exchange-wide EOD is a first-class full-market source.
p = Path("analysis/global_markets/scanner.py")
text = p.read_text(encoding="utf-8")
old = "from .eodhd_bulk import EODHDBulkEODProvider\n"
new = old + "from .euronext_live import EuronextLiveRegulatedClient\n"
if new not in text:
    if old not in text: raise SystemExit("scanner EODHD import anchor missing")
    text = text.replace(old, new, 1)
old = "        self.eodhd_bulk = EODHDBulkEODProvider(self.eodhd_api_token, timeout=max(20.0, self.timeout)) if self.eodhd_api_token else None\n"
new = old + "        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))\n"
if new not in text:
    if old not in text: raise SystemExit("scanner init anchor missing")
    text = text.replace(old, new, 1)

old = "        if not self.market_api_key and self.eodhd_bulk is None:\n            market_provider = registry.market(country, spec.code)\n"
new = "        if not self.market_api_key and self.eodhd_bulk is None and not self.euronext_live.supported(country.upper(), spec.code):\n            market_provider = registry.market(country, spec.code)\n"
if new not in text:
    if old not in text: raise SystemExit("scanner cache/live condition anchor missing")
    text = text.replace(old, new, 1)

old = '''        if self.eodhd_bulk is not None:\n            quotes, screening_errors, market_source = self.eodhd_bulk.batch_quotes(selected_universe, country.upper(), spec)\n        else:\n            quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)\n            market_source = "Twelve Data licensed batch market feed"\n'''
new = '''        if self.euronext_live.supported(country.upper(), spec.code):\n            quotes, screening_errors, market_source = self.euronext_live.batch_quotes(selected_universe, country.upper(), spec)\n        elif self.eodhd_bulk is not None:\n            quotes, screening_errors, market_source = self.eodhd_bulk.batch_quotes(selected_universe, country.upper(), spec)\n        else:\n            quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)\n            market_source = "Twelve Data licensed batch market feed"\n'''
if new not in text:
    if old not in text: raise SystemExit("scanner source preference anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Tests use fixtures only; no external calls.
Path("analysis/tests/test_global_euronext_live.py").write_text(r'''import requests

from global_markets.country_packs import get_exchange
from global_markets.euronext_live import EuronextLiveRegulatedClient
from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from global_markets.models import GlobalCompany


CSV_FIXTURE = ''' + "'''" + '''Name;ISIN;Symbol;Market;Currency;"Open Price";"High Price";"low Price";"last Price";"last Trade MIC Time";"Time Zone";Volume;Turnover;"Closing Price";"Closing Price DateTime"\n"European Equities"\n"24 Sep 2026"\n"All datapoints provided as of end of last active trading day."\n"AALBERTS NV";NL0000852564;AALB;"Euronext Amsterdam";EUR;42.30;42.44;41.80;41.96;" 17:35";CET;158332;6653141.36;41.96;\n"UNRELATED";NL0000000002;ZZZ;"Euronext Amsterdam";EUR;10;11;9;10;" 17:35";CET;0;0;10;\n''' + "'''" + '''


class FakeResponse:
    status_code = 200
    content = CSV_FIXTURE.encode("utf-8")
    def raise_for_status(self):
        return None


def test_euronext_directory_resolves_exact_isin(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    client = EuronextLiveRegulatedClient()
    resolved, meta = client.resolve_isins(
        [{"isin": "NL0000852564"}, {"isin": "NL9999999999"}],
        country="NL",
        exchange="EURONEXT_AMSTERDAM",
    )
    assert resolved["NL0000852564"]["ticker"] == "AALB"
    assert resolved["NL0000852564"]["resolver"] == "official-euronext-live-regulated"
    assert "NL9999999999" not in resolved
    assert meta["directoryRows"] == 2
    assert meta["directoryMatched"] == 1


def test_euronext_eod_intersects_authoritative_isin_universe(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    client = EuronextLiveRegulatedClient()
    quotes, errors, source = client.batch_quotes(
        [GlobalCompany(
            country="NL", exchange="EURONEXT_AMSTERDAM", currency="EUR",
            ticker="AALB", name="Aalberts N.V.", mic_code="XAMS",
            isin="NL0000852564", instrument_type="Common Stock",
        )],
        "NL",
        get_exchange("NL", "EURONEXT_AMSTERDAM"),
    )
    assert errors == []
    assert len(quotes) == 1
    assert quotes[0]["ticker"] == "AALB"
    assert quotes[0]["price"] == 41.96
    assert quotes[0]["averageVolume"] == 158332
    assert quotes[0]["liquidityValue"] == 6653141.36
    assert "Euronext regulated official EOD" in source


def test_firds_uses_euronext_before_openfigi(monkeypatch):
    provider = ESMAFIRDSOpenFIGIUniverseProvider()
    provider.euronext_directory.resolve_isins = lambda identities, country, exchange: ({
        "NL0000852564": {"ticker": "AALB", "name": "AALBERTS NV", "resolver": "official-euronext-live-regulated"}
    }, {"directoryMatched": 1})
    provider._resolve_openfigi = lambda identities, native_mic: (_ for _ in ()).throw(AssertionError("OpenFIGI should not be called"))
    resolved, missing, ambiguous, meta = provider._resolve(
        [{"isin": "NL0000852564"}],
        country="NL", exchange="EURONEXT_AMSTERDAM", native_mic="XAMS",
    )
    assert resolved["NL0000852564"]["ticker"] == "AALB"
    assert missing == {}
    assert ambiguous == {}
    assert meta["directoryMatched"] == 1
    assert meta["openfigiMatched"] == 0


def test_euronext_markets_are_available_without_paid_market_key(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    monkeypatch.delenv("BIAP_EODHD_API_TOKEN", raising=False)
    from global_markets.scanner import GlobalMarketScanner
    scanner = GlobalMarketScanner()
    assert scanner.euronext_live.supported("FR", "EURONEXT_PARIS")
    assert scanner.euronext_live.supported("IT", "EURONEXT_MILAN")
    assert scanner.euronext_live.supported("NL", "EURONEXT_AMSTERDAM")
    assert scanner.euronext_live.supported("BE", "EURONEXT_BRUSSELS")
    assert scanner.euronext_live.supported("PT", "EURONEXT_LISBON")
    assert scanner.euronext_live.supported("NO", "EURONEXT_OSLO")
''', encoding="utf-8")
