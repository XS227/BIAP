"""Read-only CODAL adapter for BIAP.

Verified sources on the BIAP production VPS:

- GET /api/search/v1/companies
- GET /api/search/v1/financialYears?Symbol=<symbol>
- GET /api/search/v2/q?... for filing discovery
- CODAL's Excel export URL, which currently returns HTML tables for financial statements

The adapter never fabricates fundamentals. Report-derived values are exposed only
when explicit financial-statement rows can be parsed from the issuer's own CODAL
filing. Missing or ambiguous fields stay unavailable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
import json
import os
import re
import time
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
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


@dataclass(frozen=True)
class CodalFundamentals:
    symbol: str
    revenue_current: float
    revenue_prev: float
    net_profit_current: float
    net_profit_prev: float
    revenue_yoy_pct: float
    net_margin_pct: float
    net_margin_prev_pct: float
    gross_profit_current: Optional[float] = None
    gross_profit_prev: Optional[float] = None
    audit_opinion: Optional[str] = None
    related_party_flags: Optional[int] = None
    guidance_note: Optional[str] = None
    tracing_no: Optional[str] = None
    report_title: Optional[str] = None
    report_url: Optional[str] = None
    source: str = "codal_financial_statement_html"

    def to_dict(self) -> dict:
        return asdict(self)


_companies_cache: tuple[float, list[dict[str, Any]]] | None = None
_years_cache: dict[str, tuple[float, list[str]]] = {}
_filings_cache: dict[str, tuple[float, list[CodalFiling]]] = {}
_financial_filings_cache: dict[str, tuple[float, list[CodalFiling]]] = {}
_fundamentals_cache: dict[str, tuple[float, Optional[CodalFundamentals]]] = {}


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
    """Return the issuer's own financial-statement filings."""
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


class _TableRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self._cell_parts: list[str] = []
        self._row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self.in_row = True
            self._row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.in_cell:
            text = " ".join("".join(self._cell_parts).split())
            self._row.append(unescape(text))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self.in_row = False


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize_text(value: str) -> str:
    return (
        value.translate(str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " ", "\u200f": " ", "\u200e": " "}))
        .replace("( ", "(")
        .replace(" )", ")")
        .strip()
    )


def _parse_number(value: str) -> Optional[float]:
    text = _normalize_text(value).translate(_PERSIAN_DIGITS)
    text = text.replace("٬", "").replace(",", "").replace("٫", ".")
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[^0-9.+-]", "", text)
    if not text or text in {"+", "-", ".", "+.", "-."}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _fetch_filing_html(filing: CodalFiling) -> str:
    if not filing.excel_url:
        raise CodalDataUnavailable("CODAL filing has no report payload URL")
    url = filing.excel_url
    if not url.lower().startswith(("http://", "https://")):
        url = urljoin("https://www.codal.ir", url)
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 BIAP/1.0",
            "Accept": "text/html,application/xhtml+xml,application/ms-excel,*/*",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=max(_TIMEOUT, 20)) as resp:
            raw = resp.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CodalDataUnavailable(f"CODAL report request failed: {exc}") from exc
    text = raw.decode("utf-8", errors="ignore")
    if "<html" not in text.lower() and "<table" not in text.lower():
        raise CodalDataUnavailable("CODAL report payload is not parseable HTML")
    return text


def _row_values(rows: list[list[str]], aliases: tuple[str, ...]) -> Optional[tuple[float, float]]:
    def canonical_label(value: str) -> str:
        return re.sub(r"\s+", "", _normalize_text(value))

    wanted = {canonical_label(alias) for alias in aliases}
    for row in rows:
        if not row:
            continue
        normalized = [_normalize_text(cell) for cell in row]
        label_idx = next(
            (
                idx
                for idx, cell in enumerate(normalized)
                if canonical_label(cell) in wanted
            ),
            None,
        )
        if label_idx is None:
            continue
        numbers = [_parse_number(cell) for cell in row[label_idx + 1 :]]
        values = [value for value in numbers if value is not None]
        if len(values) >= 2:
            return values[0], values[1]
    return None


def _parse_fundamentals(symbol: str, filing: CodalFiling, report_html: str) -> Optional[CodalFundamentals]:
    parser = _TableRows()
    parser.feed(report_html)

    revenue = _row_values(
        parser.rows,
        ("درآمدهای عملیاتی", "درآمد عملیاتی", "جمع درآمدهای عملیاتی"),
    )
    net_profit = _row_values(
        parser.rows,
        ("سود (زیان) خالص", "سود خالص", "زیان خالص"),
    )
    gross_profit = _row_values(
        parser.rows,
        ("سود (زیان) ناخالص", "سود ناخالص", "زیان ناخالص"),
    )

    if revenue is None or net_profit is None:
        return None
    revenue_current, revenue_prev = revenue
    net_profit_current, net_profit_prev = net_profit
    if revenue_current == 0 or revenue_prev == 0:
        return None

    revenue_yoy_pct = (revenue_current - revenue_prev) / abs(revenue_prev) * 100
    net_margin_pct = net_profit_current / revenue_current * 100
    net_margin_prev_pct = net_profit_prev / revenue_prev * 100

    return CodalFundamentals(
        symbol=symbol,
        revenue_current=revenue_current,
        revenue_prev=revenue_prev,
        net_profit_current=net_profit_current,
        net_profit_prev=net_profit_prev,
        gross_profit_current=gross_profit[0] if gross_profit else None,
        gross_profit_prev=gross_profit[1] if gross_profit else None,
        revenue_yoy_pct=revenue_yoy_pct,
        net_margin_pct=net_margin_pct,
        net_margin_prev_pct=net_margin_prev_pct,
        tracing_no=filing.tracing_no,
        report_title=filing.title,
        report_url=filing.excel_url,
    )


def fundamentals_for_symbol(symbol: str) -> Optional[CodalFundamentals]:
    """Parse conservative, report-derived fundamentals from CODAL.

    Only revenue and net-profit rows that are explicitly present in the issuer's
    financial-statement table are used. Audit opinion, related-party flags and
    guidance remain None until dedicated verified parsers exist.
    """
    wanted = symbol.strip()
    if not wanted:
        return None
    now = time.time()
    cached = _fundamentals_cache.get(wanted)
    if cached and now - cached[0] < _FILINGS_TTL:
        return cached[1]

    result: Optional[CodalFundamentals] = None
    for filing in latest_financial_filings(wanted, limit=3):
        if not filing.excel_url:
            continue
        try:
            report_html = _fetch_filing_html(filing)
            result = _parse_fundamentals(wanted, filing, report_html)
        except CodalDataUnavailable:
            continue
        if result is not None:
            break

    _fundamentals_cache[wanted] = (now, result)
    return result


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
