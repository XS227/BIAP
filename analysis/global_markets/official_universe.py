"""Authoritative exchange-universe providers for BIAP Global.

These adapters intentionally provide instrument identity only. Market prices and
fundamentals remain separate provider layers. A scanner may use these universes
as ranking denominators because the rows come directly from the exchange's own
published reference/listing files rather than a broad vendor search catalog.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
import xlrd

from .country_packs import get_exchange
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_USER_AGENT = "BIAP Global official-universe sync (+https://setai.no)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get(url: str, *, timeout: float) -> requests.Response:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise GlobalProviderError(f"official universe request failed: {type(exc).__name__}") from exc


def parse_deutsche_boerse_csv(
    text: str,
    *,
    country: str,
    exchange: str,
    source_url: str,
) -> list[GlobalCompany]:
    """Parse Deutsche Börse T7 `All tradable instruments` CSV.

    T7 prepends two metadata rows before the semicolon-delimited header. Only
    active Common Stock (`CS`) instruments on the requested MIC and supported
    currency are admitted to BIAP's ordinary-equity universe.
    """
    spec = get_exchange(country, exchange)
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    header_index = next((i for i, line in enumerate(lines) if line.startswith("Product Status;")), None)
    if header_index is None:
        raise GlobalProviderError("Deutsche Boerse universe header not found")

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])), delimiter=";")
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    allowed_currencies = {value.upper() for value in spec.currencies}
    accepted_mics = set(spec.accepted_mics)
    observed = _now_iso()

    for row in reader:
        if str(row.get("Product Status") or "").strip().upper() != "ACTIVE":
            continue
        if str(row.get("Instrument Status") or "").strip().upper() != "ACTIVE":
            continue
        if str(row.get("Instrument Type") or "").strip().upper() != "CS":
            continue
        mic = str(row.get("MIC Code") or "").strip().upper()
        if accepted_mics and mic not in accepted_mics:
            continue
        currency = str(row.get("Currency") or row.get("Settlement Currency") or "").strip().upper()
        if allowed_currencies and currency not in allowed_currencies:
            continue
        ticker = str(row.get("Mnemonic") or "").strip().upper()
        name = str(row.get("Instrument") or "").strip()
        isin = str(row.get("ISIN") or "").strip().upper()
        if not ticker or not name or ticker in seen:
            continue
        if len(isin) != 12 or not isin.isalnum():
            continue
        if country.upper() == "DE" and not isin.startswith("DE"):
            continue
        seen.add(ticker)
        result.append(GlobalCompany(
            country=country.upper(),
            exchange=spec.code,
            currency=currency,
            ticker=ticker,
            name=name,
            mic_code=mic or spec.mic,
            isin=isin,
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "instrument_type_code": "CS",
                "product_status": "Active",
                "instrument_status": "Active",
                "primary_market_mic": str(row.get("Primary Market MIC Code") or "").strip().upper() or None,
                "market_segment": str(row.get("Market Segment") or "").strip() or None,
                "country_of_issue": str(row.get("Country Of Issue") or "").strip() or None,
                "domestic_scope": f"ISIN:{country.upper()}",
            },
            sources=[SourceEvidence(
                provider="official-deutsche-boerse-t7-universe",
                source_type="official_exchange_universe",
                source_id=f"{spec.code}:{ticker}",
                source_url=source_url,
                observed_at=observed,
                quality=1.0,
                notes="Deutsche Boerse T7 official All tradable instruments; active common stock, domestic ISIN scope only.",
            )],
        ))
    if not result:
        raise GlobalProviderError(f"Deutsche Boerse returned no active common stocks for {spec.code}")
    return result


def parse_asx_rows(rows: Iterable[Iterable[object]], *, source_url: str) -> list[GlobalCompany]:
    """Normalize the ASX complete ISIN directory to ordinary fully-paid shares."""
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    observed = _now_iso()
    for values in rows:
        cells = list(values)
        if len(cells) < 4:
            continue
        ticker = str(cells[0] or "").strip().upper()
        name = str(cells[1] or "").strip()
        security_type = str(cells[2] or "").strip().upper()
        isin = str(cells[3] or "").strip().upper()
        # The official file contains options and other securities alongside the
        # equity line. Keep the ordinary fully-paid equity security only.
        if not security_type.startswith("ORDINARY FULLY PAID"):
            continue
        if not ticker or not name or ticker in seen:
            continue
        if len(isin) != 12 or not isin.isalnum():
            continue
        if not isin.startswith("AU"):
            continue
        seen.add(ticker)
        result.append(GlobalCompany(
            country="AU",
            exchange="ASX",
            currency="AUD",
            ticker=ticker,
            name=name,
            mic_code="XASX",
            isin=isin,
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "asx_security_type": security_type,
                "domestic_scope": "ISIN:AU",
            },
            sources=[SourceEvidence(
                provider="official-asx-isin-universe",
                source_type="official_exchange_universe",
                source_id=f"ASX:{ticker}",
                source_url=source_url,
                observed_at=observed,
                quality=1.0,
                notes="ASX complete ISIN directory; ordinary fully-paid Australian-ISIN securities only.",
            )],
        ))
    if not result:
        raise GlobalProviderError("ASX official ISIN directory returned no ordinary fully-paid equities")
    return result


class DeutscheBoerseUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-deutsche-boerse-t7-universe"

    _PAGES = {
        "XETRA": (
            "https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/xetra-downloads",
            "t7-xetr-alltradableinstruments.csv",
        ),
        "FRANKFURT": (
            "https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/frankfurt-downloads",
            "t7-xfra-bf-alltradableinstruments.csv",
        ),
    }

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(5.0, float(timeout))

    def _download_url(self, exchange: str) -> str:
        try:
            page_url, token = self._PAGES[exchange.upper()]
        except KeyError as exc:
            raise GlobalProviderError(f"unsupported Deutsche Boerse exchange {exchange}") from exc
        html = _http_get(page_url, timeout=self.timeout).text
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
        token_lower = token.lower()
        for href in hrefs:
            if token_lower in href.lower():
                return urljoin(page_url, href)

        # Deutsche Boerse occasionally changes the blob filename casing while
        # keeping the semantic file name stable. Fall back to exchange marker +
        # All Tradable Instruments instead of failing a daily official refresh.
        exchange_marker = "xetr" if exchange.upper() == "XETRA" else "xfra"
        for href in hrefs:
            low = href.lower()
            if exchange_marker in low and "alltradableinstruments.csv" in low:
                return urljoin(page_url, href)
        raise GlobalProviderError(f"official Deutsche Boerse CSV link not found for {exchange}")

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if (country or "").upper() != "DE" or not exchange:
            raise GlobalProviderError("Deutsche Boerse universe requires DE and XETRA/FRANKFURT")
        url = self._download_url(exchange)
        response = _http_get(url, timeout=self.timeout)
        text = response.content.decode("utf-8-sig", errors="replace")
        return parse_deutsche_boerse_csv(text, country="DE", exchange=exchange, source_url=url)


class ASXUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-asx-isin-universe"
    source_url = "https://www.asx.com.au/content/dam/asx/issuers/ISIN.xls"

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(5.0, float(timeout))

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None) -> Iterable[GlobalCompany]:
        if (country or "").upper() != "AU" or (exchange or "").upper() != "ASX":
            raise GlobalProviderError("ASX universe requires AU/ASX")
        response = _http_get(self.source_url, timeout=self.timeout)
        try:
            book = xlrd.open_workbook(file_contents=response.content)
            sheet = book.sheet_by_index(0)
        except Exception as exc:
            raise GlobalProviderError(f"ASX ISIN workbook parse failed: {type(exc).__name__}") from exc
        rows = ([sheet.cell_value(r, c) for c in range(min(4, sheet.ncols))] for r in range(sheet.nrows))
        return parse_asx_rows(rows, source_url=self.source_url)
