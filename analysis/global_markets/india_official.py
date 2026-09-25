"""Official NSE ordinary-equity universe for BIAP Global.

NSE publishes the current Equity-segment security master as EQUITY_L.csv.
BIAP admits only SERIES=EQ rows from that official file. ETFs, debt, warrants,
REIT/InvIT files and other instrument families are published separately by NSE
and therefore never enter this universe.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import re
from typing import Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_PAGE_URL = "https://www.nseindia.com/static/market-data/securities-available-for-trading"
_PROVIDER_ID = "official-nse-equity-security-master"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"


def _key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def _int(value: object) -> Optional[int]:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_nse_equity_csv(content: bytes | str) -> list[GlobalCompany]:
    if isinstance(content, bytes):
        text = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = content.decode("latin-1", errors="replace")
    else:
        text = content

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise GlobalProviderError("NSE equity security master has no header")

    result: list[GlobalCompany] = []
    seen: set[str] = set()
    observed = datetime.now(timezone.utc).isoformat()

    for source in reader:
        row = {_key(k): str(v or "").strip() for k, v in source.items() if k is not None}
        series = row.get("SERIES", "").upper()
        if series != "EQ":
            continue
        ticker = row.get("SYMBOL", "").upper()
        name = row.get("NAME OF COMPANY", "") or ticker
        isin = row.get("ISIN NUMBER", "").upper() or None
        if not ticker or not name or ticker in seen:
            continue
        if isin and (len(isin) != 12 or not isin.isalnum()):
            isin = None
        seen.add(ticker)
        result.append(GlobalCompany(
            country="IN",
            exchange="NSE",
            currency="INR",
            ticker=ticker,
            name=name,
            mic_code="XNSE",
            isin=isin,
            instrument_type="Common Stock",
            lot_size=_int(row.get("MARKET LOT")),
            raw_provider_fields={
                "official_universe": True,
                "nse_series": series,
                "nse_date_of_listing": row.get("DATE OF LISTING") or None,
                "nse_paid_up_value": row.get("PAID UP VALUE") or None,
                "nse_face_value": row.get("FACE VALUE") or None,
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"NSE:{ticker}",
                source_url=_SOURCE_URL,
                observed_at=observed,
                quality=1.0,
                notes="NSE official Equity-segment security master; SERIES=EQ only.",
            )],
        ))

    if not result:
        raise GlobalProviderError("NSE official security master returned no EQ ordinary equities")
    return result


class NSEOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = max(5.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("IN", "NSE")

    def _download(self) -> bytes:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv,text/plain,*/*",
            "Referer": _PAGE_URL,
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            response = requests.get(self.source_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"NSE official security master request failed: {type(exc).__name__}") from exc
        if len(response.content) < 5_000:
            raise GlobalProviderError("NSE official security master payload is unexpectedly small")
        return response.content

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"NSE official universe is not configured for {country}/{exchange}")
        result = parse_nse_equity_csv(self._download())
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XNSE",
            "identitySource": "NSE Securities available for Equity segment (EQUITY_L.csv)",
            "sourceUrl": self.source_url,
        }
        return result
