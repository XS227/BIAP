"""Official Tokyo Stock Exchange ordinary-equity universe from JPX.

JPX's monthly "List of TSE-listed Issues" is the membership source. BIAP keeps
only domestic Prime/Standard/Growth listings with a standard four-character TSE
local code. This excludes ETFs/ETNs, REIT/fund products, PRO Market, foreign
listings and five-digit preferred/bond-type class shares.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from typing import Optional

import openpyxl
import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider

_LIST_URL = (
    "https://www.jpx.co.jp/english/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_e.xlsx"
)
_PROVIDER = "official-jpx-tse-listed-issues"
_DOMESTIC = {
    "primemarket(domestic)",
    "standardmarket(domestic)",
    "growthmarket(domestic)",
}
_CODE_RE = re.compile(r"^[0-9A-Z]{4}$")


def _text(value: object) -> str:
    return str(value or "").strip()


def _section_key(value: object) -> str:
    return re.sub(r"\s+", "", _text(value)).lower()


def _code(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _text(value).upper()


def is_jpx_domestic_common(code: object, section: object) -> bool:
    return bool(_CODE_RE.fullmatch(_code(code))) and _section_key(section) in _DOMESTIC


def parse_jpx_workbook(data: bytes) -> tuple[str, list[dict]]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(value or "").strip() for value in next(rows)]
    except Exception as exc:
        raise GlobalProviderError(f"JPX listed-issues workbook is invalid: {type(exc).__name__}") from exc

    index = {name: i for i, name in enumerate(header)}
    required = {"Effective Date", "Local Code", "Name (English)", "Section/Products"}
    if not required.issubset(index):
        raise GlobalProviderError("JPX listed-issues workbook is missing required columns")

    effective = ""
    parsed: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        code = _code(row[index["Local Code"]])
        section = _text(row[index["Section/Products"]])
        if not is_jpx_domestic_common(code, section) or code in seen:
            continue
        name = _text(row[index["Name (English)"]])
        if not name:
            continue
        date_value = _text(row[index["Effective Date"]])
        effective = max(effective, date_value)
        parsed.append({
            "code": code,
            "name": name,
            "section": section,
            "effectiveDate": date_value,
            "sector33Code": _text(row[index["33 Sector(Code)"]]) if "33 Sector(Code)" in index else None,
            "sector33Name": _text(row[index["33 Sector(name)"]]) if "33 Sector(name)" in index else None,
            "sector17Code": _text(row[index["17 Sector(Code)"]]) if "17 Sector(Code)" in index else None,
            "sector17Name": _text(row[index["17 Sector(name)"]]) if "17 Sector(name)" in index else None,
            "sizeCode": _text(row[index["Size Code (New Index Series)"]]) if "Size Code (New Index Series)" in index else None,
            "sizeName": _text(row[index["Size (New Index Series)"]]) if "Size (New Index Series)" in index else None,
        })
        seen.add(code)
    if not parsed:
        raise GlobalProviderError("JPX listed-issues workbook returned no domestic ordinary equities")
    return effective, parsed


class JPXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    def _download(self) -> bytes:
        try:
            response = requests.get(
                _LIST_URL,
                headers={
                    "User-Agent": "BIAP Global market-data integration (+https://setai.no)",
                    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"JPX listed-issues request failed: {type(exc).__name__}") from exc
        if not response.content.startswith(b"PK"):
            raise GlobalProviderError("JPX listed-issues response is not an XLSX workbook")
        return response.content

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if str(country or "").upper() != "JP" or str(exchange or "").upper() != "TSE_JP":
            raise GlobalProviderError(f"JPX universe is not configured for {country}/{exchange}")
        effective, rows = parse_jpx_workbook(self._download())
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            result.append(GlobalCompany(
                country="JP",
                exchange="TSE_JP",
                currency="JPY",
                ticker=row["code"],
                name=row["name"],
                mic_code="XJPX",
                instrument_type="Common Stock",
                sector=row.get("sector17Name") or None,
                industry=row.get("sector33Name") or None,
                raw_provider_fields={
                    "official_universe": True,
                    "trusted_official_equity": True,
                    "jpx_effective_date": row.get("effectiveDate"),
                    "jpx_section": row.get("section"),
                    "jpx_sector_33_code": row.get("sector33Code"),
                    "jpx_sector_17_code": row.get("sector17Code"),
                    "jpx_size_code": row.get("sizeCode"),
                    "jpx_size_name": row.get("sizeName"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_reference",
                    source_id=f"JPX-TSE-LIST-{effective or 'current'}",
                    source_url=_LIST_URL,
                    observed_at=observed,
                    period_end=effective or None,
                    quality=0.99,
                    notes="JPX List of TSE-listed Issues; domestic Prime/Standard/Growth ordinary-equity scope.",
                )],
            ))
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "effectiveDate": effective,
            "identitySource": "JPX List of TSE-listed Issues",
            "filter": "Prime/Standard/Growth domestic + standard 4-character TSE local code",
        }
        return result
