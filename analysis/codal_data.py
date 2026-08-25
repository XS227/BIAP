"""Read-only CODAL adapter for BIAP.

Verified sources on the BIAP production VPS:

- GET /api/search/v1/companies
- GET /api/search/v1/financialYears?Symbol=<symbol>
- GET /api/search/v2/q?... for filing discovery

CODAL's v2 search endpoint was live-verified across multiple industries
(steel, petrochemical, auto, detergent, cement, food) with Length=12.
Financial-statement discovery is filtered with LetterType=6 and Childs=false
so BIAP selects the issuer's own financial reports instead of assembly notices
or subsidiary filings.

This adapter never fabricates fundamentals. It exposes verified metadata and
raw filing-discovery metadata only. `codal` fundamentals remain unavailable
until report payloads are parsed into explicit revenue/margin/audit fields.
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
_FILINGS_TTL = 5 * 60
_CODAL_PAGE_LENGTH = 12
_FINANCIAL_LETTER_TYPE = 6


class CodalDataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CodalFiling:
    tracing_no: Optional[str]
    title: Optional[str]
    sent_at: Optional[str]
    publish_at: Optional[str]
    letter_code: Optional[str]
    url: Optional[str]
    pdf_url: Optional[str]
    excel_url: Optional[str]
    attachment_url: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CodalMetadata:
    symbol: str
    company_name: Optional[str]
    company_id: Optional[str]
    financial_years: list[str]
    latest_filings: list[dict]
    latest_financial_filings: list[dict]
    source: str = "search.codal.ir"

    def to_dict(self) -> dict:
        return asdict(self)


_companies_cache: tuple[float, list[dict[str, Any]]] | None = None
_years_cache: dict[str, tuple[float, list[str]]] = {}
_filings_cache: dict[str, tuple[float, list[CodalFiling]]] = {}
_financial_filings_cache: dict[str, tuple[float, list[CodalFiling]]] = {}


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


def _pick(row: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _normalize_filing(row: dict[str, Any]) -> CodalFiling:
    """Normalize only identifiers/links/timestamps that CODAL itself returns."""
    return CodalFiling(
        tracing_no=_pick(row, "TracingNo", "TracingNumber"),
        title=_pick(row, "Title"),
        sent_at=_pick(row, "SentDateTime", "SentDate"),
        publish_at=_pick(row, "PublishDateTime", "PublishDate"),
        letter_code=_pick(row, "LetterCode", "LetterType"),
        url=_pick(row, "Url", "URL"),
        pdf_url=_pick(row, "PdfUrl", "PDFUrl"),
        excel_url=_pick(row, "ExcelUrl", "ExcelURL"),
        attachment_url=_pick(row, "AttachmentUrl", "AttachmentURL"),
    )


def _search_payload(symbol: str, params: dict[str, Any]) -> list[CodalFiling]:
    payload = _get_json("/api/search/v2/q", {"Symbol": symbol, **params})
    if not isinstance(payload, dict):
        return []
    rows = payload.get("Letters")
    if not isinstance(rows, list):
        return []
    return [_normalize_filing(row) for row in rows if isinstance(row, dict)]


def latest_filings(symbol: str, limit: int = 5) -> list[CodalFiling]:
    """Return recent CODAL filings using the live-verified query shape."""
    wanted = symbol.strip()
    if not wanted:
        return []
    limit = max(1, min(int(limit), _CODAL_PAGE_LENGTH))

    now = time.time()
    cached = _filings_cache.get(wanted)
    if cached and now - cached[0] < _FILINGS_TTL:
        return cached[1][:limit]

    attempts = [
        {
            "PageNumber": 1,
            "Length": _CODAL_PAGE_LENGTH,
            "CompanyState": 0,
            "CompanyType": -1,
            "FromDate": "1404/01/01",
            "ToDate": "1405/12/29",
            "Mains": "true",
            "Childs": "true",
            "Publisher": "false",
            "search": "true",
        },
        {
            "PageNumber": 1,
            "Length": _CODAL_PAGE_LENGTH,
            "CompanyState": -1,
            "CompanyType": -1,
            "FromDate": "1404/01/01",
            "ToDate": "1405/12/29",
            "Mains": "true",
            "Childs": "true",
            "Publisher": "false",
            "search": "true",
        },
        {"PageNumber": 1, "Length": _CODAL_PAGE_LENGTH},
    ]

    filings: list[CodalFiling] = []
    for params in attempts:
        try:
            filings = _search_payload(wanted, params)
        except CodalDataUnavailable:
            continue
        if filings:
            break

    _filings_cache[wanted] = (now, filings)
    return filings[:limit]


def latest_financial_filings(symbol: str, limit: int = 3) -> list[CodalFiling]:
    """Return the issuer's own financial-statement filings.

    Live-verified across multiple Tehran-market industries. LetterType=6
    selects financial statements, while Childs=false excludes subsidiaries.
    We intentionally return raw CODAL filing metadata only; parsing numbers is
    a separate step so missing or inaccessible report payloads cannot become
    fabricated fundamentals.
    """
    wanted = symbol.strip()
    if not wanted:
        return []
    limit = max(1, min(int(limit), _CODAL_PAGE_LENGTH))

    now = time.time()
    cached = _financial_filings_cache.get(wanted)
    if cached and now - cached[0] < _FILINGS_TTL:
        return cached[1][:limit]

    attempts = [
        {
            "LetterType": _FINANCIAL_LETTER_TYPE,
            "PageNumber": 1,
            "Length": _CODAL_PAGE_LENGTH,
            "CompanyState": 0,
            "CompanyType": -1,
            "Mains": "true",
            "Childs": "false",
            "Publisher": "false",
            "search": "true",
        },
        {
            "LetterType": _FINANCIAL_LETTER_TYPE,
            "PageNumber": 1,
            "Length": _CODAL_PAGE_LENGTH,
            "CompanyState": -1,
            "CompanyType": -1,
            "Mains": "true",
            "Childs": "false",
            "Publisher": "false",
            "search": "true",
        },
    ]

    filings: list[CodalFiling] = []
    for params in attempts:
        try:
            filings = _search_payload(wanted, params)
        except CodalDataUnavailable:
            continue
        if filings:
            break

    _financial_filings_cache[wanted] = (now, filings)
    return filings[:limit]


def metadata_for_symbol(symbol: str) -> Optional[CodalMetadata]:
    company = find_company(symbol)
    if company is None:
        return None
    years = financial_years(symbol)
    filings = latest_filings(symbol, limit=5)
    financial_filings = latest_financial_filings(symbol, limit=3)
    return CodalMetadata(
        symbol=symbol,
        company_name=(str(company.get("n")).strip() if company.get("n") else None),
        company_id=(str(company.get("i")).strip() if company.get("i") else None),
        financial_years=years,
        latest_filings=[item.to_dict() for item in filings],
        latest_financial_filings=[item.to_dict() for item in financial_filings],
    )
