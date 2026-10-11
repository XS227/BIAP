"""Conservative, issuer-agnostic extraction of primary statements from official PDFs.

Markets without a machine-readable filing feed (CH, SG, NZ, SA, ZA, ...) publish
audited annual reports as PDFs. This module turns the *text layer* of such a
report into normalized fundamentals with page-level provenance. It contains no
issuer-specific values or layouts; every acceptance rule is generic and
fail-closed:

* the statement page must carry the expected reporting period as its primary
  date (so prior-year comparative pages, interim reports and transition periods
  are never read as the annual statement);
* the value column is located by header year *and* position, never by "first
  number on the row"; Group/Company or Consolidated/Separate columns are told
  apart by their header scope, and company-only columns are never used;
* the unit scale (millions / thousands / ...) and the reporting currency must be
  stated on the statement itself and agree with the expectation;
* total_assets = total_liabilities + total_equity must hold (liabilities printed
  as negatives are normalized), otherwise the whole extraction is rejected;
* a field matched by several rows or pages with different values is rejected,
  not guessed;
* an unqualified audit opinion on the consolidated statements must be found;
  qualified/adverse/disclaimed or unrecognised opinions reject the document.

A PDF existing is therefore never enough: callers receive either a fully
validated :class:`StatementExtraction` or a :class:`PDFExtractionError`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import io
import re
from typing import Any, Iterable, Mapping, Optional

from .providers import GlobalProviderError

EXTRACTOR_VERSION = "pdf-statements-v1"
MAX_PDF_BYTES = 60 * 1024 * 1024
MAX_PAGES = 700


class PDFExtractionError(GlobalProviderError):
    """The document cannot be used as recommendation-grade evidence."""


# --------------------------------------------------------------------------- #
# PDF -> page text
# --------------------------------------------------------------------------- #
def read_pdf_pages(content: bytes) -> dict[int, str]:
    """1-based page number -> layout-preserving text. Pages that fail are empty."""
    from pypdf import PdfReader

    if not content.startswith(b"%PDF"):
        raise PDFExtractionError("source is not a PDF document")
    if len(content) > MAX_PDF_BYTES:
        raise PDFExtractionError("PDF exceeds the supported size")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - defensive
            raise PDFExtractionError("PDF is encrypted") from exc
    if len(reader.pages) > MAX_PAGES:
        raise PDFExtractionError("PDF has too many pages")
    pages: dict[int, str] = {}
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            text = ""
        if len(text.strip()) < 20:
            # Layout mode drops text drawn through a rotated text matrix (e.g. an
            # auditor's report whose page is /Rotate 0 but whose text is rotated),
            # returning an empty page. Plain extraction still reads it; the
            # statement parsers do not need column layout for such pages.
            try:
                plain = page.extract_text() or ""
            except Exception:
                plain = ""
            if len(plain.strip()) > len(text.strip()):
                text = plain
        pages[index] = text
    return pages


# --------------------------------------------------------------------------- #
# Text primitives
# --------------------------------------------------------------------------- #
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ \t]+({_MONTH_RE})\.?,?[ \t]+((?:19|20)\d{{2}})\b", re.I)
_DATE_MDY = re.compile(rf"\b({_MONTH_RE})\.?[ \t]+(\d{{1,2}}),?[ \t]+((?:19|20)\d{{2}})\b", re.I)
_YEAR_CHUNK = re.compile(r"^(?:(?:19|20)\d{2})$")
_NUM_TOKEN = re.compile(
    r"^\(?[-−–]?\d{1,3}(?:[, ]\d{3})*(?:\.\d+)?\)?[%^*]*$"
    r"|^\(?[-−–]?\d+(?:\.\d+)?\)?[%^*]*$"
    r"|^[–—−-]\*?$"
)
_SIMPLE_NUM = re.compile(r"^\(?[-−–]?\d[\d,]*(?:\.\d+)?\)?[%^*]*$|^[–—−-]\*?$")


def spaceless(text: str) -> str:
    """Lower-case letters only: robust to PDF letter-spacing ("To t a l  e q u i t y")."""
    return re.sub(r"[^a-z]", "", str(text or "").lower())


def _dates_in(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for m in _DATE_DMY.finditer(text):
        found.append((m.start(), _iso(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))))
    for m in _DATE_MDY.finditer(text):
        found.append((m.start(), _iso(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))))
    return [(pos, iso) for pos, iso in sorted(found) if iso]


def _iso(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def parse_number(text: str) -> Optional[float]:
    """Parse a printed statement amount. Dash = 0; unparsable/'less than' = None."""
    t = str(text or "").strip().replace(" ", " ")
    if not t:
        return None
    if re.fullmatch(r"[–—−-]", t):
        return 0.0
    t = t.rstrip("^*%").strip()
    if not t or t in {"-", "–", "—", "−"}:
        return None  # "-*" (= less than one unit) is ambiguous: reject
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()
    elif t.startswith("(") or t.endswith(")"):
        return None
    if t[:1] in "-−–":
        negative, t = True, t[1:].strip()
    t = t.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    value = float(t)
    return -value if negative else value


# --------------------------------------------------------------------------- #
# Layout model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Chunk:
    text: str
    start: int
    end: int

    @property
    def center(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass(frozen=True)
class Cell:
    text: str
    value: Optional[float]
    center: float


@dataclass
class Segment:
    label: str
    key: str
    cells: list[Cell]
    start: int


@dataclass
class HeaderColumn:
    year: Optional[int]
    center: float
    scope: Optional[str]  # "group" | "company" | None | "notes"


def _split_chunks(line: str, *, space_thousands: bool) -> list[Chunk]:
    line = re.sub(r"(?<=\d\))(?=[A-Za-z])", "  ", line)  # "(750.1)Other" glue
    line = re.sub(r"(?<=\d\.\d) (?=[A-Z][a-z]{2,})", "  ", line)  # "2,308.4 Profit after tax" side-by-side glue
    raw = [Chunk(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|\s*$)", line)]
    raw = _join_split_labels(line, raw)
    chunks: list[Chunk] = []
    for chunk in raw:
        tokens = chunk.text.split(" ")
        numeric = all(_NUM_TOKEN.match(t) or _SIMPLE_NUM.match(t) for t in tokens if t)
        if numeric and len(tokens) > 1 and not space_thousands:
            pos = chunk.start
            for token in tokens:
                if token:
                    chunks.append(Chunk(token, pos, pos + len(token)))
                pos += len(token) + 1
            continue
        chunks.append(chunk)
    return chunks


def _join_split_labels(line: str, raw: list[Chunk]) -> list[Chunk]:
    """Re-join a label that the PDF printed with a double space ("Profit  for the period").

    Only a two-space gap between two non-numeric chunks, the second starting in
    lower case, is joined; real column gaps are wider. A wrong join can only
    make a label unrecognisable (field missing -> rejection), never move a value.
    """
    joined: list[Chunk] = []
    for chunk in raw:
        prev = joined[-1] if joined else None
        if (
            prev is not None
            and chunk.start - prev.end == 2
            and prev.text[-1:].isalpha()
            and chunk.text[:1].islower()
            and not _is_number_chunk(prev.text)
            and not _is_number_chunk(chunk.text)
        ):
            joined[-1] = Chunk(f"{prev.text} {chunk.text}", prev.start, chunk.end)
        else:
            joined.append(chunk)
    return joined


_NOTE_REFS = re.compile(r"^\d{1,2}(?:\.\d+)?(?:/\d{1,2}(?:\.\d+)?)+$")


def _is_number_chunk(text: str) -> bool:
    return bool(_NUM_TOKEN.match(text) or _SIMPLE_NUM.match(text))


_NOTE_TAIL = re.compile(r"^(.*[A-Za-z)\]])[\s.]*((?:\d{1,2}(?:\.\d+)?\s*,?\s*)+)$")


def _label_and_note(text: str) -> tuple[str, Optional[str]]:
    m = _NOTE_TAIL.match(text.strip())
    if m and len(m.group(2).replace(" ", "")) <= 12:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), None


@dataclass
class PageModel:
    number: int
    text: str
    lines: list[str]
    head: list[str]
    foot: list[str]
    space_thousands: bool

    @classmethod
    def build(cls, number: int, text: str) -> "PageModel":
        lines = [ln.rstrip() for ln in str(text or "").splitlines() if ln.strip()]
        sample = "\n".join(lines)
        comma = bool(re.search(r"\d,\d{3}\b", sample))
        space = bool(re.search(r"(?<![\d,.])\d{1,3} \d{3}(?![\d,])", sample))
        return cls(number, text, lines, lines[:16], lines[-4:], space and not comma)


_KIND_PATTERNS = {
    "balance": re.compile(r"statements?offinancialposition|balancesheets?|statements?offinancialcondition"),
    "income": re.compile(
        r"incomestatements?|statements?ofprofitorloss|statements?ofcomprehensiveincome|"
        r"statements?ofincome|statements?ofearnings|profitandlossaccount|statements?ofoperations"
    ),
    "cashflow": re.compile(r"statements?ofcashflows?|cashflowstatements?"),
}


def _title_kinds(lines: list[str]) -> dict[str, str]:
    keys = [spaceless(line) for line in lines]
    candidates = list(keys) + [a + b for a, b in zip(keys, keys[1:])]
    # side-by-side statements: titles wrap inside their own column block
    blocks = [[spaceless(c) for c in re.split(r"\s{3,}", line.strip())] for line in lines]
    for upper, lower in zip(blocks, blocks[1:]):
        if len(upper) == len(lower) and len(upper) > 1:
            candidates.extend(a + b for a, b in zip(upper, lower))
    kinds: dict[str, str] = {}
    for key in candidates:
        if not key or re.match(r"^(?:notesto|notetothe|notestothe)", key):
            continue
        for kind, pattern in _KIND_PATTERNS.items():
            if pattern.search(key):
                kinds.setdefault(kind, key)
    return kinds


def page_kinds(page: PageModel) -> dict[str, str]:
    """kind -> spaceless title text that identified it. Page head wins; footer titles
    identify continuation pages that repeat the statement name at the bottom."""
    return _title_kinds(page.head[:10]) or _title_kinds(page.foot)


# --------------------------------------------------------------------------- #
# Header, units, currency
# --------------------------------------------------------------------------- #
_SCOPE_GROUP = re.compile(r"^(group|consolidated)$", re.I)
_SCOPE_COMPANY = re.compile(r"^(company|separate|parent|parent company|bank)$", re.I)
_HEADER_DATE = re.compile(rf"^(?:\d{{1,2}}\s+(?:{_MONTH_RE})\.?\s+(?:19|20)\d{{2}}|(?:{_MONTH_RE})\.?\s+\d{{1,2}},?\s+(?:19|20)\d{{2}})$", re.I)


def _year_of(chunk_text: str) -> Optional[int]:
    t = chunk_text.strip()
    if _YEAR_CHUNK.match(t):
        return int(t)
    if _HEADER_DATE.match(t):
        return int(re.search(r"(?:19|20)\d{2}", t).group(0))  # type: ignore[union-attr]
    return None


def header_columns(page: PageModel) -> list[HeaderColumn]:
    zone_end = len(page.lines)
    for index, line in enumerate(page.lines[:40]):
        chunks = _split_chunks(line, space_thousands=page.space_thousands)
        has_label = any(re.search(r"[A-Za-z]{4,}", c.text) and not _SCOPE_GROUP.match(c.text) and not _SCOPE_COMPANY.match(c.text) and _year_of(c.text) is None for c in chunks)
        has_amount = any(_is_number_chunk(c.text) and _year_of(c.text) is None and len(c.text.replace(",", "")) >= 1 for c in chunks)
        if has_label and has_amount and index > 0:
            zone_end = index
            break
    columns: list[HeaderColumn] = []
    scopes: list[tuple[str, float]] = []
    notes: list[float] = []
    for line in page.lines[:zone_end]:
        for chunk in _split_chunks(line, space_thousands=page.space_thousands):
            year = _year_of(chunk.text)
            if year is not None:
                columns.append(HeaderColumn(year, chunk.center, None))
            elif _SCOPE_GROUP.match(chunk.text.strip()):
                scopes.append(("group", chunk.center))
            elif _SCOPE_COMPANY.match(chunk.text.strip()):
                scopes.append(("company", chunk.center))
            elif re.fullmatch(r"notes?", chunk.text.strip(), re.I):
                notes.append(chunk.center)
    if not columns:
        return []
    for column in columns:
        if scopes:
            nearest = min(scopes, key=lambda s: abs(s[1] - column.center))
            if abs(nearest[1] - column.center) <= 40:
                column.scope = nearest[0]
    for center in notes:
        columns.append(HeaderColumn(None, center, "notes"))
    return columns


_SCALE_PATTERNS = (
    (1e9, re.compile(r"\bbillions?\b|\bbn\b", re.I)),
    (1e6, re.compile(r"\bmillions?\b|\bmn\b", re.I)),
    (1e3, re.compile(r"\bthousands?\b|\b000s\b", re.I)),
)
_SCALE_SYMBOLS = (
    (1e9, re.compile(r"(?:\b[A-Z]{1,3}\$|[\$£€])\s?bn\b|\bR['’]?\s?bn\b")),
    (1e6, re.compile(r"(?:\b[A-Z]{1,3}\$|[\$£€])\s?[mM]\b|\bR['’]?\s?m\b|\b[A-Z]{3}\s?[mM]\b")),
    (1e3, re.compile(r"['’‘`]000\b|\$\s?000\b|\b[A-Z]{3}\s?['’]?000\b")),
)

# Currency markers: code -> (regexes found in a statement head, regexes for full-text names)
_CURRENCY_MARKERS: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "CHF": (re.compile(r"\bCHF\b"), re.compile(r"swiss francs?", re.I)),
    "SGD": (re.compile(r"\bS\$|\bSGD\b"), re.compile(r"singapore dollars?", re.I)),
    "NZD": (re.compile(r"\bNZ\$|\bNZD\b"), re.compile(r"new zealand dollars?", re.I)),
    "ZAR": (re.compile(r"\bR['’]?\s?(?:m|000|bn)\b|\bZAR\b"), re.compile(r"south african rands?|\brands?\b", re.I)),
    "SAR": (re.compile(r"\bSAR\b|\bSR['’]?\s?(?:m|000)\b"), re.compile(r"saudi riyals?|saudi arabian riyals?|\bSAR\b", re.I)),
    "AUD": (re.compile(r"\bA\$|\bAUD\b"), re.compile(r"australian dollars?", re.I)),
    "CAD": (re.compile(r"\bC\$|\bCAD\b"), re.compile(r"canadian dollars?", re.I)),
    "HKD": (re.compile(r"\bHK\$|\bHKD\b"), re.compile(r"hong kong dollars?", re.I)),
    "USD": (re.compile(r"\bUS\$|\bUSD\b|(?<![A-Za-z])\$"), re.compile(r"u\.?s\.? dollars?", re.I)),
    "EUR": (re.compile(r"€|\bEUR\b"), re.compile(r"\beuros?\b", re.I)),
    "GBP": (re.compile(r"£|\bGBP\b"), re.compile(r"pound sterling|british pounds?", re.I)),
}


def statement_scale(page: PageModel) -> Optional[float]:
    zone = " ".join(page.head[:12])
    hits = {scale for scale, pattern in _SCALE_PATTERNS if pattern.search(zone)}
    hits |= {scale for scale, pattern in _SCALE_SYMBOLS if pattern.search(zone)}
    return hits.pop() if len(hits) == 1 else None


def head_currencies(page: PageModel) -> set[str]:
    zone = " ".join(page.head[:12])
    return {code for code, (head_re, _) in _CURRENCY_MARKERS.items() if head_re.search(zone)}


def _duration_ok(page: PageModel, kind: str) -> bool:
    if kind == "balance":
        return True
    zone = " ".join(page.head[:12]).lower()
    if re.search(r"\b(?:three|six|nine|[1-9]|10|11)\s+months\b|transition(?:al)?\s+period|\bquarter\b", zone):
        return False
    return True


# --------------------------------------------------------------------------- #
# Row extraction
# --------------------------------------------------------------------------- #
def page_segments(page: PageModel, header_end: Optional[int] = None) -> list[tuple[int, Segment]]:
    """(line index, labelled segment with numeric cells) for every data row."""
    rows: list[tuple[int, Segment]] = []
    for index, line in enumerate(page.lines):
        chunks = _split_chunks(line, space_thousands=page.space_thousands)
        segments: list[Segment] = []
        for chunk in chunks:
            if _NOTE_REFS.match(chunk.text) and segments:
                # multi-note reference such as "8/9" or "3/17/19": a note cell, never a value
                segments[-1].cells.append(Cell(chunk.text, None, chunk.center))
            elif _is_number_chunk(chunk.text) and segments:
                segments[-1].cells.append(Cell(chunk.text, parse_number(chunk.text), chunk.center))
            elif not _is_number_chunk(chunk.text):
                label, note = _label_and_note(chunk.text)
                seg = Segment(label=label, key=spaceless(label), cells=[], start=chunk.start)
                if note:
                    seg.cells.append(Cell(note, None, chunk.end + 1.0))
                segments.append(seg)
        for seg in segments:
            if seg.key:
                rows.append((index, seg))
    return rows


def _nearest_column(cell: Cell, columns: list[HeaderColumn], tolerance: float) -> Optional[HeaderColumn]:
    best = min(columns, key=lambda c: abs(c.center - cell.center))
    return best if abs(best.center - cell.center) <= tolerance else None


def _column_tolerance(columns: list[HeaderColumn]) -> float:
    centers = sorted({round(c.center, 1) for c in columns})
    gaps = [b - a for a, b in zip(centers, centers[1:]) if b - a > 1.0]
    return max(6.0, 0.5 * min(gaps)) if gaps else 12.0


def _year_blocks(columns: list[HeaderColumn]) -> list[list[HeaderColumn]]:
    """Year columns split into side-by-side blocks (a block never repeats a year/scope)."""
    blocks: list[list[HeaderColumn]] = []
    current: list[HeaderColumn] = []
    for col in sorted((c for c in columns if c.year is not None), key=lambda c: c.center):
        if any(c.year == col.year and c.scope == col.scope for c in current):
            blocks.append(current)
            current = []
        current.append(col)
    if current:
        blocks.append(current)
    return blocks


def _ordered_mapping(segment: Segment, columns: list[HeaderColumn]) -> Optional[list[tuple[Cell, HeaderColumn]]]:
    """Map a row's value cells to a header block by order (robust to horizontal drift)."""
    blocks = _year_blocks(columns)
    cells = list(segment.cells)
    if not cells or not blocks:
        return None
    candidates = []
    for block in blocks:
        n = len(block)
        values = cells[1:] if len(cells) == n + 1 and re.fullmatch(r"\d{1,2}", cells[0].text) else cells
        if len(values) == n:
            mean_cells = sum(c.center for c in values) / n
            mean_block = sum(c.center for c in block) / n
            candidates.append((abs(mean_cells - mean_block), list(zip(values, block))))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def pick_values(
    segment: Segment, columns: list[HeaderColumn], period_year: int, tolerance: float
) -> Optional[tuple[Optional[float], Optional[float], Optional[str]]]:
    """(current, prior, scope) for a row, or None when the column mapping is ambiguous.

    Cells are mapped by order inside the nearest header block when the cell count matches the
    block (layout text drifts horizontally between rows, so nearest-header position can pick the
    prior-year cell); otherwise by position, rejecting two cells that fight for one column.
    """
    ordered = _ordered_mapping(segment, columns)
    mapped: dict[int, tuple[Cell, HeaderColumn]] = {}
    for cell in segment.cells:
        column = _nearest_column(cell, columns, tolerance)
        if column is None:
            continue
        if id(column) in {id(c) for _, c in mapped.values()}:
            positional_ok = False
            mapped = {}
            break
        mapped[id(cell)] = (cell, column)
    else:
        positional_ok = True
    if ordered is not None:
        pairs = ordered
    elif positional_ok:
        pairs = list(mapped.values())
    else:
        return None
    current = [(c, col) for c, col in pairs if col.year == period_year and col.scope in (None, "group")]
    if len(current) != 1:
        return None
    cell, col = current[0]
    prior = [(c, pc) for c, pc in pairs if pc.year == period_year - 1 and pc.scope == col.scope]
    prior_value = prior[0][0].value if len(prior) == 1 else None
    return cell.value, prior_value, col.scope


# --------------------------------------------------------------------------- #
# Field catalogue (labels only; never company values)
# --------------------------------------------------------------------------- #
FIELD_TIERS: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "balance": {
        "total_assets": (("totalassets",),),
        "total_liabilities": (("totalliabilities",),),
        "total_equity": (("totalequity", "totalshareholdersequity", "totalequityandreserves", "totalstockholdersequity", "totalnetassets",
                         "totalequityattributabletoshareholders"), ("equity",)),
        "total_equity_and_liabilities": (("totalequityandliabilities", "totalliabilitiesandequity", "totalequityandliabilitiesandreserves"),),
        "current_assets": (("totalcurrentassets", "currentassets"),),
        "current_liabilities": (("totalcurrentliabilities", "currentliabilities"),),
        "cash_and_equivalents": (("cashandcashequivalents", "cashandbankbalances", "cashandequivalents", "cashandcashequivalent"),),
    },
    "income": {
        "revenue": (
            ("revenue", "revenues", "totalrevenue", "totalrevenues", "operatingrevenue", "totaloperatingrevenue",
             "netrevenue", "revenuefromcontractswithcustomers", "revenuefromcontractswithcustomer"),
            ("turnover", "netsales", "sales", "salesrevenue", "totalsales"),
        ),
        "gross_profit": (("grossprofit",),),
        "operating_income": (("operatingprofit", "operatingincome", "resultsfromoperatingactivities", "profitfromoperatingactivities", "profitfromoperations"),),
    },
    "cashflow": {
        "operating_cash_flow": (
            ("netcashfromoperatingactivities", "netcashinflowsfromoperatingactivities", "netcashinflowfromoperatingactivities",
             "netcashgeneratedfromoperatingactivities", "totalcashflowsfromoperatingactivities", "netcashprovidedbyoperatingactivities",
             "netcashflowsfromoperatingactivities", "netcashgeneratedbyoperatingactivities", "cashflowsfromoperatingactivitiesnet"),
        ),
    },
}

_NET_INCOME_TOTAL = {"profitfortheyear", "netprofitfortheyear", "profitaftertax", "netincome", "profitfortheperiod",
                     "netprofit", "profitfortheyearfromcontinuingoperations", "profitattheyear", "profitaftertaxation",
                     "netearnings", "netprofitaftertax"}
_ATTRIB_START = re.compile(r"^(profit|netincome|netprofit|earnings|lossprofit|profitloss)?attributableto$|^attributableto$")
_OWNERS = re.compile(
    r"^(?:.*)(?:ownersof(?:the)?(?:company|parent|group|[a-z]{0,25})|equityholdersof(?:the)?(?:company|parent|group|[a-z]{0,25})|"
    r"shareholdersof(?:the)?(?:company|parent|group|[a-z]{0,25})|shareholders|equityholders|ownersoftheparent)$"
)
_ATTRIB_STOP = re.compile(r"^(earningspershare|basic|diluted|totalcomprehensive|otherwise|headline)")


@dataclass
class Figure:
    field: str
    value: float          # full reporting units (scale applied)
    prior: Optional[float]
    page: int
    label: str
    raw: str
    scale: float
    scope: Optional[str]


def _match_tier(key: str, tiers: tuple[tuple[str, ...], ...]) -> Optional[int]:
    for index, tier in enumerate(tiers):
        if key in tier:
            return index
    return None


@dataclass
class StatementExtraction:
    period_end: str
    currency: str
    figures: dict[str, Figure]
    derived: dict[str, dict[str, Any]]
    rejected: dict[str, str]
    checks: dict[str, Any]
    audit_opinion: str
    audit_pages: list[int]
    identity_pages: list[int]
    statement_pages: dict[str, list[int]]

    def values(self) -> dict[str, float]:
        out = {name: fig.value for name, fig in self.figures.items() if not name.startswith("_")}
        for name, info in self.derived.items():
            out[name] = info["value"]
        return out

    def provenance(self) -> dict[str, Any]:
        prov: dict[str, Any] = {}
        for name, fig in self.figures.items():
            if name.startswith("_"):
                continue
            prov[name] = {"page": fig.page, "label": fig.label, "raw": fig.raw, "scale": fig.scale, "scope": fig.scope or "consolidated"}
        for name, info in self.derived.items():
            prov[name] = {k: v for k, v in info.items() if k != "value"} | {"derived": True}
        return prov


_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ \t]+({_MONTH_RE})\b(?!\.?,?[ \t]+(?:19|20)\d{{2}})", re.I)


def _primary_period_ok(page: PageModel, columns: list[HeaderColumn], expected: str) -> bool:
    """The statement's own period must be the expected one (never a comparative page)."""
    head = "\n".join(page.head)
    dated = _dates_in(head)
    if dated:
        return dated[0][1] == expected
    # Some reports print "for the year ended 31 August" and put the years in the column header.
    years = [c.year for c in columns if c.year is not None]
    if not years or max(years) != int(expected[:4]):
        return False
    for m in _DAY_MONTH.finditer(head):
        if _iso(int(expected[:4]), _MONTHS[m.group(2).lower()], int(m.group(1))) == expected:
            return True
    return False


def _collect(
    page: PageModel, kind: str, title_key: str, period_year: int, expected_period: str, problems: list[str],
) -> list[tuple[str, int, Figure, Optional[float]]]:
    """Candidate (field, tier, figure, prior) from one statement page."""
    columns = header_columns(page)
    if not columns or not any(c.year == period_year for c in columns):
        problems.append(f"p{page.number}: no header column for {period_year}")
        return []
    if not _primary_period_ok(page, columns, expected_period):
        problems.append(f"p{page.number}: primary period is not {expected_period}")
        return []
    if not _duration_ok(page, kind):
        problems.append(f"p{page.number}: not a 12-month period")
        return []
    scale = statement_scale(page)
    if scale is None:
        problems.append(f"p{page.number}: unit scale not stated unambiguously")
        return []
    has_scope_header = any(c.scope == "group" for c in columns)
    if not re.search(r"consolidated|group", title_key) and not has_scope_header:
        problems.append(f"p{page.number}: not a consolidated/group statement")
        return []
    tolerance = _column_tolerance(columns)
    wanted = FIELD_TIERS[kind]
    found: list[tuple[str, int, Figure, Optional[float]]] = []
    in_attrib = False
    saw_nci = False
    for _, segment in page_segments(page):
        key = segment.key
        picked = pick_values(segment, columns, period_year, tolerance) if segment.cells else None
        if kind == "income":
            if "noncontrollinginterest" in key or "minority" in key:
                saw_nci = True
            if _ATTRIB_START.match(key):
                in_attrib = True
                continue
            if in_attrib and _ATTRIB_STOP.match(key):
                in_attrib = False
        if picked is None or picked[0] is None:
            continue
        value, prior, scope = picked
        for name, tiers in wanted.items():
            tier = _match_tier(key, tiers)
            if tier is not None:
                found.append((name, tier, _fig(name, value, prior, page, segment, scale, scope), prior))
        if kind == "income":
            if in_attrib and "noncontrolling" not in key and "minority" not in key and _OWNERS.match(key):
                found.append(("net_income", 0, _fig("net_income", value, prior, page, segment, scale, scope), prior))
            elif key in _NET_INCOME_TOTAL:
                found.append(("net_income", 1, _fig("net_income", value, prior, page, segment, scale, scope), prior))
    if kind == "income" and saw_nci:
        found.append(("_saw_nci", 0, Figure("_saw_nci", 1.0, None, page.number, "", "", 1.0, None), None))
    return found


def _fig(name: str, value: float, prior: Optional[float], page: PageModel, seg: Segment, scale: float, scope: Optional[str]) -> Figure:
    return Figure(
        field=name,
        value=value * scale,
        prior=None if prior is None else prior * scale,
        page=page.number,
        label=seg.label,
        raw=" ".join(c.text for c in seg.cells),
        scale=scale,
        scope=scope,
    )


# --------------------------------------------------------------------------- #
# Audit opinion and identity
# --------------------------------------------------------------------------- #
_AUDIT_TITLE = re.compile(r"independentauditor|auditorsreport|auditorreport|reportoftheindependentauditor|statutoryauditorsreport|reportoftheauditor")
_TRUE_AND_FAIR = re.compile(r"presentfairly|trueandfairview|presentsfairly|giveatrueandfair|fairlypresent")
_NEGATIVE_OPINION = re.compile(
    r"basisforqualifiedopinion|basisforadverseopinion|basisfordisclaimerofopinion|adverseopinion|"
    r"disclaimerofopinion|wedonotexpressanopinion|donotexpressanopinion|qualifiedopinion(?!s?on)|"
    r"exceptfortheeffectsof|exceptforthepossibleeffects|basisforqualified"
)


def detect_audit_opinion(pages: Mapping[int, PageModel], legal_core: str) -> tuple[str, list[int]]:
    """'unqualified' only when an auditor's report page states a clean opinion on consolidated statements."""
    clean: list[int] = []
    for number, page in pages.items():
        head_key = spaceless(" ".join(page.head[:6] + page.foot))
        if not _AUDIT_TITLE.search(head_key):
            continue
        body = spaceless(page.text)
        if "opinion" not in body:
            continue
        if _TRUE_AND_FAIR.search(body) and "consolidated" in body:
            if re.search(r"basisforqualified|basisforadverse|basisfordisclaimer|exceptfortheeffects|adverseopinion|disclaimerofopinion|donotexpressanopinion", body):
                raise PDFExtractionError(f"auditor report on p{number} is not an unqualified opinion")
            clean.append(number)
    if not clean:
        raise PDFExtractionError("no unqualified auditor opinion on consolidated statements found")
    return "unqualified", clean


def _name_core(name: str) -> str:
    text = spaceless(name)
    for suffix in ("limited", "ltd", "plc", "inc", "corporation", "corp", "company", "holdingsltd", "holding", "holdings", "group", "ag", "sa", "nv", "se", "co", "asa", "pjsc", "psc"):
        if text.endswith(suffix) and len(text) - len(suffix) >= 4:
            text = text[: -len(suffix)]
    return text


def verify_identity(pages: Mapping[int, PageModel], legal_name: str, *, minimum_pages: int = 2) -> list[int]:
    core = _name_core(legal_name)
    if len(core) < 4:
        raise PDFExtractionError("legal name too short to verify")
    hits = [n for n, p in pages.items() if core in spaceless(p.text)]
    if len(hits) < minimum_pages:
        raise PDFExtractionError(f"issuer name {legal_name!r} not found in the document")
    return hits[:12]


_DOLLAR_FAMILY = {"AUD", "CAD", "NZD", "SGD", "HKD", "USD"}


def confirm_currency(statement_pages: list[PageModel], all_pages: Mapping[int, PageModel], expected: str) -> str:
    expected = expected.upper()
    if expected not in _CURRENCY_MARKERS:
        raise PDFExtractionError(f"unsupported reporting currency {expected}")
    heads: set[str] = set()
    for page in statement_pages:
        heads |= head_currencies(page)
    # A bare '$' is ambiguous only inside the dollar family (A$/NZ$/S$ reports often print '$000');
    # for any other expected currency a USD marker is a contradiction, and an explicit US$/USD
    # marker contradicts every non-USD expectation.
    explicit_usd = any(re.search(r"\bUS\$|\bUSD\b", " ".join(p.head[:12])) for p in statement_pages)
    ignorable = {"USD"} if expected in _DOLLAR_FAMILY and not explicit_usd else set()
    other = {c for c in heads if c != expected and c not in ignorable}
    if other:
        raise PDFExtractionError(f"statement currency markers {sorted(other)} contradict expected {expected}")
    if expected in heads:
        return "statement_head"
    name_re = _CURRENCY_MARKERS[expected][1]
    if any(name_re.search(p.text) for p in all_pages.values()):
        return "document_text"
    raise PDFExtractionError(f"reporting currency {expected} is not stated in the document")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def extract_primary_statements(
    pages: Mapping[int, str],
    *,
    expected_period_end: str,
    expected_currency: str,
    legal_name: str,
) -> StatementExtraction:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected_period_end or ""):
        raise PDFExtractionError("expected period end must be ISO date")
    period_year = int(expected_period_end[:4])
    models = {n: PageModel.build(n, t) for n, t in sorted(pages.items())}
    identity_pages = verify_identity(models, legal_name)
    audit_opinion, audit_pages = detect_audit_opinion(models, _name_core(legal_name))

    problems: list[str] = []
    collected: dict[str, list[tuple[str, int, Figure, Optional[float]]]] = {"balance": [], "income": [], "cashflow": []}
    statement_pages: dict[str, list[int]] = {"balance": [], "income": [], "cashflow": []}
    used_pages: list[PageModel] = []
    for number, page in models.items():
        for kind, title_key in page_kinds(page).items():
            found = _collect(page, kind, title_key, period_year, expected_period_end, problems)
            if found:
                collected[kind].extend(found)
                statement_pages[kind].append(number)
                used_pages.append(page)
    if not collected["balance"]:
        raise PDFExtractionError("no balance sheet for the expected period found: " + "; ".join(problems[:4]))

    figures: dict[str, Figure] = {}
    rejected: dict[str, str] = {}
    for kind, items in collected.items():
        by_field: dict[str, list[tuple[int, Figure]]] = {}
        for name, tier, fig, _ in items:
            by_field.setdefault(name, []).append((tier, fig))
        for name, candidates in by_field.items():
            best_tier = min(t for t, _ in candidates)
            tier_figs = [f for t, f in candidates if t == best_tier]
            values = {round(f.value, 4) for f in tier_figs}
            if len(values) > 1:
                pages_txt = ",".join(str(f.page) for f in tier_figs)
                rejected[name] = f"conflicting values on pages {pages_txt}"
                continue
            figures[name] = tier_figs[0]

    saw_nci = "_saw_nci" in figures
    if "net_income" in figures and figures["net_income"].label and saw_nci:
        label_key = spaceless(figures["net_income"].label)
        if label_key in _NET_INCOME_TOTAL and not _OWNERS.match(label_key):
            # profit for the year (incl. non-controlling interests) only: owners' share not read
            rejected["net_income"] = "non-controlling interest present but owners' share not isolated"
            del figures["net_income"]

    scale_set = {f.scale for f in figures.values()}
    currency_source = confirm_currency(used_pages, models, expected_currency)

    # ---- balance-sheet validation ---------------------------------------------------------
    for needed in ("total_assets", "total_equity"):
        if needed not in figures:
            raise PDFExtractionError(f"balance sheet {needed} not found/ambiguous: {rejected.get(needed, 'missing')}")
    assets = figures["total_assets"].value
    equity = figures["total_equity"].value
    derived: dict[str, dict[str, Any]] = {}
    checks: dict[str, Any] = {}
    unit = min(scale_set) if scale_set else 1.0
    tolerance = max(2.0 * unit, abs(assets) * 5e-4)
    if assets <= 0:
        raise PDFExtractionError("total assets is not positive")
    if "total_liabilities" in figures:
        liabilities = abs(figures["total_liabilities"].value)
        figures["total_liabilities"].value = liabilities
        if abs(assets - liabilities - equity) > tolerance:
            raise PDFExtractionError("balance sheet identity failed: assets != liabilities + equity")
        checks["assets_equal_liabilities_plus_equity"] = True
    else:
        tie = figures.get("total_equity_and_liabilities")
        if tie is None or abs(abs(tie.value) - assets) > tolerance:
            raise PDFExtractionError("total liabilities not stated and not verifiable from total equity and liabilities")
        derived["total_liabilities"] = {
            "value": assets - equity, "method": "total_assets - total_equity",
            "page": figures["total_assets"].page, "tiedTo": "total equity and liabilities",
        }
        checks["assets_equal_liabilities_plus_equity"] = "derived"
    if "total_equity_and_liabilities" in figures:
        checks["total_equity_and_liabilities_ties"] = abs(abs(figures["total_equity_and_liabilities"].value) - assets) <= tolerance
        if not checks["total_equity_and_liabilities_ties"]:
            raise PDFExtractionError("total equity and liabilities differs from total assets")
    for name in ("current_assets", "cash_and_equivalents"):
        if name in figures and figures[name].value > assets * (1 + 1e-9):
            rejected[name] = "exceeds total assets"
            del figures[name]
    if "current_liabilities" in figures:
        figures["current_liabilities"].value = abs(figures["current_liabilities"].value)

    for required in ("revenue", "net_income"):
        if required not in figures:
            raise PDFExtractionError(f"income statement {required} not found/ambiguous: {rejected.get(required, 'missing')}")
    revenue = figures["revenue"].value
    if revenue <= 0:
        raise PDFExtractionError("revenue is not positive")
    if abs(figures["net_income"].value) > 3 * revenue:
        raise PDFExtractionError("net income implausible relative to revenue")
    if "gross_profit" in figures and figures["gross_profit"].value > revenue * (1 + 1e-9):
        rejected["gross_profit"] = "exceeds revenue"
        del figures["gross_profit"]
    prior = figures["revenue"].prior
    if prior is not None and prior > 0:
        ratio = revenue / prior
        if not 0.05 < ratio < 20:
            raise PDFExtractionError("revenue change versus prior year is implausible")
        checks["revenue_prior_ratio"] = round(ratio, 4)
        derived["revenue_prev"] = {"value": prior, "method": "prior-year column of the revenue row", "page": figures["revenue"].page}

    figures.pop("_saw_nci", None)
    figures.pop("total_equity_and_liabilities", None)
    return StatementExtraction(
        period_end=expected_period_end,
        currency=expected_currency.upper(),
        figures=figures,
        derived=derived,
        rejected=rejected,
        checks={**checks, "currency_source": currency_source, "problems": problems[:12]},
        audit_opinion=audit_opinion,
        audit_pages=audit_pages[:6],
        identity_pages=identity_pages,
        statement_pages={k: v for k, v in statement_pages.items() if v},
    )
