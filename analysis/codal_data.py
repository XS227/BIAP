"""Read-only CODAL adapter for BIAP.

This module deliberately starts with metadata that we have verified against
search.codal.ir from the BIAP server:

- GET /api/search/v1/companies
- GET /api/search/v1/financialYears?Symbol=<symbol>

The v2 letter search endpoint is reachable but currently returns an empty
letter set for the tested فولاد query, so this adapter does NOT fabricate
fundamental metrics from incomplete data. It exposes company identity and
financial-year metadata only. Fundamental availability remains false until
actual report values are parsed and normalized in a later step.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import time
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE = "https://search.codal.ir"
_TIMEOUT = 8
_COMPANIES_TTL = 6 * 60 * 60
_YEARS_TTL = 60 * 60


class CodalDataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CodalMetadata:
    symbol: str
    company_name: Optional[str]
    company_id: Optional[str]
    financial_years: list[str]
    source: str = "search.codal.ir"

    def to_dict(self) -> dict:
        return asdict(self)


_companies_cache: tuple[float, list[dict[str, Any]]] | None = None
_years_cache: dict[str, tuple[float, list[str]]] = {}


def base_url() -> str:
    return os.getenv("BIAP_CODAL_BASE", DEFAULT_BASE).rstrip("/")


def _get_json(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    url = f"{base_url()}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 BIAP/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CodalDataUnavailable(f"CODAL request failed: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CodalDataUnavailable("CODAL returned invalid JSON") from exc


def list_companies() -> list[dict[str, Any]]:
    global _companies_cache
    now = time.time()
    if _companies_cache and now - _companies_cache[0] < _COMPANIES_TTL:
        return _companies_cache[1]

    payload = _get_json("/api/search/v1/companies")
    if not isinstance(payload, list):
        raise CodalDataUnavailable("unexpected CODAL companies response")
    companies = [row for row in payload if isinstance(row, dict)]
    _companies_cache = (now, companies)
    return companies


def find_company(symbol: str) -> Optional[dict[str, Any]]:
    wanted = symbol.strip()
    if not wanted:
        return None
    for row in list_companies():
        if str(row.get("sy", "")).strip() == wanted:
            return row
    return None


def financial_years(symbol: str) -> list[str]:
    wanted = symbol.strip()
    if not wanted:
        return []
    now = time.time()
    cached = _years_cache.get(wanted)
    if cached and now - cached[0] < _YEARS_TTL:
        return cached[1]

    payload = _get_json("/api/search/v1/financialYears", {"Symbol": wanted})
    years: list[str] = []
    if isinstance(payload, list):
        years = [str(v) for v in payload if isinstance(v, (str, int, float))]
    _years_cache[wanted] = (now, years)
    return years


def metadata_for_symbol(symbol: str) -> Optional[CodalMetadata]:
    company = find_company(symbol)
    if company is None:
        return None
    years = financial_years(symbol)
    return CodalMetadata(
        symbol=symbol,
        company_name=(str(company.get("n")).strip() if company.get("n") else None),
        company_id=(str(company.get("i")).strip() if company.get("i") else None),
        financial_years=years,
    )
