"""Authoritative TSX / TSX Venture issuer universe from TMX.

TMX publishes a current workbook at a stable resource URL. The workbook mixes
operating issuers with ETFs/ETPs, CDRs, closed-end funds and CPC shells, so BIAP
admits only domestic Canadian operating-company issuer rows to the stock-ranking
universe. Market prices and fundamentals remain separate provider layers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from typing import Iterable, Optional

import openpyxl
import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://www.tsx.com/en/resource/571"
_USER_AGENT = "BIAP Global TMX universe (+https://setai.no)"

_BLOCKED_SECTOR_MARKERS = (
    "ETP",
    "EXCHANGE TRADED",
    "CLOSED-END FUND",
    "CLOSED END FUND",
    "CDR",
    "CAPITAL POOL",
)
_BLOCKED_SP_MARKERS = (
    "EXCHANGE TRADED FUND",
    "FUND OF ",
    "FI TRUST",
    "CDR",
)


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()


def _headers(row: Iterable[object]) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, value in enumerate(row):
        key = _norm(value).upper()
        if key:
            result[key] = index
    return result


def _get(values: list[object], headers: dict[str, int], *names: str) -> str:
    for name in names:
        index = headers.get(name.upper())
        if index is not None and index < len(values):
            value = _norm(values[index])
            if value:
                return value
    return ""


def _is_operating_company(values: list[object], headers: dict[str, int]) -> bool:
    sector = _get(values, headers, "Sector").upper()
    sub_sector = _get(values, headers, "Sub Sector", "Sub-Sector").upper()
    listing_type = _get(values, headers, "Listing Type").upper()
    sp_type = _get(values, headers, "SP_Type", "SP Type").upper()
    sp_sub = _get(values, headers, "SP_Sub", "SP Sub").upper()
    fund_family = _get(values, headers, "Fund Family/Issuing Entity").upper()
    combined = " | ".join((sector, sub_sector, sp_type, sp_sub, fund_family))

    if any(marker in combined for marker in _BLOCKED_SECTOR_MARKERS):
        return False
    if any(marker in combined for marker in _BLOCKED_SP_MARKERS):
        return False
    if sector == "CPC" or "IPO/CPC" in listing_type:
        return False
    # TMX uses the root-ticker .P convention for active capital-pool shells.
    ticker = _get(values, headers, "Root Ticker").upper()
    if ticker.endswith(".P"):
        return False
    return True


def parse_tmx_issuer_rows(
    rows: Iterable[Iterable[object]],
    *,
    exchange: str,
    source_url: str = _SOURCE_URL,
) -> list[GlobalCompany]:
    """Parse one TMX issuer worksheet into BIAP domestic operating equities."""
    exchange = exchange.upper()
    if exchange not in {"TSX", "TSXV"}:
        raise GlobalProviderError(f"unsupported TMX exchange {exchange}")

    materialized = [list(row) for row in rows]
    header_index: Optional[int] = None
    headers: dict[str, int] = {}
    for idx, values in enumerate(materialized):
        candidate = _headers(values)
        if "EXCHANGE" in candidate and "NAME" in candidate and "ROOT TICKER" in candidate:
            header_index = idx
            headers = candidate
            break
    if header_index is None:
        raise GlobalProviderError(f"TMX {exchange} issuer header not found")

    mic = "XTSE" if exchange == "TSX" else "XTSX"
    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()

    for values in materialized[header_index + 1 :]:
        row_exchange = _get(values, headers, "Exchange").upper()
        if row_exchange != exchange:
            continue
        ticker = _get(values, headers, "Root Ticker").upper()
        name = _get(values, headers, "Name")
        hq_region = _get(values, headers, "HQ Region")
        if not ticker or not name or ticker in seen:
            continue
        # "This market = Canada" is a domestic-company universe, not all foreign
        # secondary listings or depositary products trading on a Canadian venue.
        if hq_region.upper() != "CANADA":
            continue
        if not _is_operating_company(values, headers):
            continue

        seen.add(ticker)
        sector = _get(values, headers, "Sector") or None
        sub_sector = _get(values, headers, "Sub Sector", "Sub-Sector") or None
        co_id = _get(values, headers, "Co_ID") or None
        result.append(GlobalCompany(
            country="CA",
            exchange=exchange,
            currency="CAD",
            ticker=ticker,
            name=name,
            mic_code=mic,
            instrument_type="Common Stock",
            sector=sector,
            industry=sub_sector,
            raw_provider_fields={
                "official_universe": True,
                "tmx_co_id": co_id,
                "tmx_sector": sector,
                "tmx_sub_sector": sub_sector,
                "tmx_hq_location": _get(values, headers, "HQ Location") or None,
                "tmx_hq_region": hq_region,
                "tmx_listing_type": _get(values, headers, "Listing Type") or None,
                "tmx_listing_date": _get(values, headers, "Listing Date") or None,
                "domestic_scope": "TMX HQ Region: Canada",
            },
            sources=[SourceEvidence(
                provider="official-tmx-listed-issuers",
                source_type="official_exchange_universe",
                source_id=f"{exchange}:{co_id or ticker}",
                source_url=source_url,
                observed_at=observed,
                quality=1.0,
                notes="TMX current listed-issuer workbook; domestic Canadian operating issuers only; funds/ETPs/CDRs/CPC shells excluded.",
            )],
        ))

    if not result:
        raise GlobalProviderError(f"TMX workbook returned no eligible domestic operating issuers for {exchange}")
    return result


class TMXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-tmx-listed-issuers"
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    def _download(self) -> tuple[bytes, Optional[str]]:
        try:
            response = requests.get(
                self.source_url,
                timeout=self.timeout,
                headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"TMX issuer workbook request failed: {type(exc).__name__}") from exc
        disposition = response.headers.get("content-disposition") or ""
        match = re.search(r'filename="?([^";]+)', disposition, flags=re.I)
        filename = match.group(1) if match else None
        return response.content, filename

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if (country or "").upper() != "CA" or (exchange or "").upper() not in {"TSX", "TSXV"}:
            raise GlobalProviderError("TMX universe requires CA and TSX/TSXV")
        wanted = str(exchange).upper()
        content, filename = self._download()
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise GlobalProviderError(f"TMX issuer workbook parse failed: {type(exc).__name__}") from exc

        prefix = "TSX Issuers" if wanted == "TSX" else "TSXV Issuers"
        worksheet = next((ws for ws in workbook.worksheets if ws.title.startswith(prefix)), None)
        if worksheet is None:
            raise GlobalProviderError(f"TMX issuer workbook has no {wanted} worksheet")
        rows = list(worksheet.iter_rows(values_only=True))
        result = parse_tmx_issuer_rows(rows, exchange=wanted, source_url=self.source_url)
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "workbookFilename": filename,
            "identitySource": "TMX current TSX/TSXV listed issuer workbook",
            "domesticScope": "HQ Region Canada; operating issuers only",
        }
        return result
