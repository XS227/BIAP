"""Strict text normalizer for German official annual reports.

This module is intentionally conservative. It accepts only statement rows that
can be tied to a reporting period and a financial-statement section. It never
fills missing values with market/vendor estimates. Derived liabilities are
allowed only from the accounting identity Assets = Liabilities + Equity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Optional

from .providers import GlobalProviderError


_SPACE = re.compile(r"[ \t\u00a0]+")
_NUMBER = re.compile(r"(?<![A-Za-z])[-−–]?\(?\d[\d .,'’]*\d|[-−–]?\(?\d\)?")
_YEAR = re.compile(r"\b(20\d{2})\b")

_BALANCE_MARKERS = (
    "konzernbilanz",
    "consolidated statement of financial position",
    "consolidated balance sheet",
    "bilanz",
)
_INCOME_MARKERS = (
    "konzern-gewinn- und verlustrechnung",
    "konzerngewinn- und verlustrechnung",
    "consolidated income statement",
    "consolidated statement of profit or loss",
    "gewinn- und verlustrechnung",
)
_CASHFLOW_MARKERS = (
    "konzern-kapitalflussrechnung",
    "konzernkapitalflussrechnung",
    "consolidated statement of cash flows",
    "consolidated cash flow statement",
    "kapitalflussrechnung",
)

_ALIASES = {
    "revenue": (
        "umsatzerlöse", "umsatzerloese", "revenue", "sales revenue",
    ),
    "operating_income": (
        "betriebsergebnis", "operating profit", "operating income", "ebit",
    ),
    "ebitda": ("ebitda",),
    "net_income": (
        "konzernergebnis", "jahresüberschuss", "jahresueberschuss",
        "jahresfehlbetrag", "profit for the year", "loss for the year",
        "net income", "earnings after tax",
    ),
    "total_assets": ("summe aktiva", "bilanzsumme", "total assets"),
    "total_liabilities": (
        "summe schulden", "summe verbindlichkeiten", "total liabilities",
    ),
    "total_equity": ("eigenkapital", "total equity", "shareholders' equity"),
    "retained_earnings": ("gewinnrücklagen", "gewinnruecklagen", "retained earnings"),
    "current_assets": ("umlaufvermögen", "umlaufvermoegen", "current assets"),
    "current_liabilities": (
        "kurzfristige verbindlichkeiten", "kurzfristige schulden", "current liabilities",
    ),
    "cash_and_equivalents": (
        "zahlungsmittel und zahlungsmitteläquivalente",
        "zahlungsmittel und zahlungsmittelaequivalente",
        "liquide mittel", "cash and cash equivalents",
    ),
    "operating_cash_flow": (
        "cashflow aus laufender geschäftstätigkeit",
        "cashflow aus laufender geschaeftstaetigkeit",
        "cash flow aus laufender geschäftstätigkeit",
        "cash flows from operating activities",
        "cash flow from operating activities",
    ),
    "total_debt": (
        "finanzverbindlichkeiten", "financial liabilities", "interest-bearing debt",
        "borrowings",
    ),
    "interest_expense": ("zinsaufwendungen", "interest expense", "interest expenses"),
    "eps": ("ergebnis je aktie", "earnings per share", "eps"),
}

_SECTION_FOR_FIELD = {
    "revenue": _INCOME_MARKERS,
    "operating_income": _INCOME_MARKERS,
    "ebitda": _INCOME_MARKERS,
    "net_income": _INCOME_MARKERS,
    "total_assets": _BALANCE_MARKERS,
    "total_liabilities": _BALANCE_MARKERS,
    "total_equity": _BALANCE_MARKERS,
    "retained_earnings": _BALANCE_MARKERS,
    "current_assets": _BALANCE_MARKERS,
    "current_liabilities": _BALANCE_MARKERS,
    "cash_and_equivalents": _BALANCE_MARKERS,
    "operating_cash_flow": _CASHFLOW_MARKERS,
    "total_debt": _BALANCE_MARKERS,
    "interest_expense": _INCOME_MARKERS,
    "eps": _INCOME_MARKERS,
}


@dataclass(frozen=True)
class ParsedGermanReport:
    period_end: str
    currency: str
    report_scope: str
    audited: bool
    fundamentals: dict[str, float]
    derived_fields: tuple[str, ...]


def _normalize_lines(text: str) -> str:
    lines = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        line = _SPACE.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _parse_number(token: str) -> Optional[float]:
    raw = str(token or "").strip().replace("\u2212", "-").replace("–", "-")
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")"))
    raw = raw.strip("-() ").replace("'", "").replace("’", "").replace(" ", "")
    if not raw or not any(ch.isdigit() for ch in raw):
        return None
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1):
            raw = "".join(parts)
        else:
            raw = raw.replace(",", ".")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1):
            raw = "".join(parts)
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _nearest_multiplier(text: str, pos: int) -> float:
    window = text[max(0, pos - 800):pos].lower()
    hits: list[tuple[int, float]] = []
    patterns = (
        (r"\b(?:in|angaben in)\s+(?:mio\.?|million)\s*(?:eur|€)", 1_000_000.0),
        (r"\b(?:in|angaben in)\s+(?:teur|keur|thousand\s+euros?|eur\s+thousand)", 1_000.0),
        (r"\b(?:in|angaben in)\s+(?:eur|€)\b", 1.0),
    )
    for pattern, multiplier in patterns:
        for m in re.finditer(pattern, window, re.I):
            hits.append((m.start(), multiplier))
    return max(hits, default=(-1, 1.0), key=lambda x: x[0])[1]


def _statement_windows(text: str, markers: tuple[str, ...]) -> list[tuple[int, int]]:
    low = text.lower()
    starts = []
    for marker in markers:
        start = 0
        while True:
            idx = low.find(marker, start)
            if idx < 0:
                break
            starts.append(idx)
            start = idx + len(marker)
    if not starts:
        return [(0, len(text))]
    all_markers = tuple(dict.fromkeys(_BALANCE_MARKERS + _INCOME_MARKERS + _CASHFLOW_MARKERS))
    windows: list[tuple[int, int]] = []
    for s in sorted(set(starts)):
        next_positions = [
            low.find(marker, s + 20)
            for marker in all_markers
            if low.find(marker, s + 20) >= 0
        ]
        end = min(next_positions) if next_positions else min(len(text), s + 18000)
        windows.append((s, max(s + 500, end)))
    return windows


def _row_candidates(text: str, aliases: tuple[str, ...], windows: list[tuple[int, int]]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for start, end in windows:
        segment = text[start:end]
        low = segment.lower()
        for alias in aliases:
            cursor = 0
            alias_low = alias.lower()
            while True:
                i = low.find(alias_low, cursor)
                if i < 0:
                    break
                absolute = start + i
                tail = segment[i + len(alias): i + len(alias) + 180]
                tokens = [m.group(0) for m in _NUMBER.finditer(tail)]
                values = []
                for token in tokens[:6]:
                    value = _parse_number(token)
                    if value is None:
                        continue
                    if 1900 <= abs(value) <= 2100 and float(value).is_integer():
                        continue
                    values.append((token, value))
                if values:
                    # Statement rows commonly contain a note number before the
                    # current/prior-year values. When 3+ numeric cells exist,
                    # discard the first small cell as the note reference.
                    if len(values) >= 3 and abs(values[0][1]) < 100:
                        values = values[1:]
                    if values:
                        multiplier = _nearest_multiplier(text, absolute)
                        out.append((absolute, values[0][1] * multiplier))
                cursor = i + len(alias_low)
    return out


def _extract_field(text: str, field: str) -> Optional[float]:
    windows = _statement_windows(text, _SECTION_FOR_FIELD[field])
    candidates = _row_candidates(text, _ALIASES[field], windows)
    if not candidates:
        return None
    # Prefer the earliest row inside the first matching statement block. Notes
    # and management commentary normally occur later in the document.
    return sorted(candidates, key=lambda x: x[0])[0][1]


def _period_end(text: str, expected_year: Optional[int]) -> str:
    year = int(expected_year) if expected_year else None
    patterns = (
        re.compile(r"\b(3[01]|[12]\d|0?[1-9])\.(0?[1-9]|1[0-2])\.(20\d{2})\b"),
        re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-(3[01]|[12]\d|0[1-9])\b"),
    )
    dates: list[date] = []
    for pattern in patterns:
        for m in pattern.finditer(text[:30000]):
            try:
                if pattern is patterns[0]:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                else:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if year is None or d.year == year:
                dates.append(d)
    if dates:
        # Prefer the latest date in the expected fiscal year. Publication dates
        # are usually in the following year and are therefore excluded.
        return max(dates).isoformat()
    if year is not None:
        annual = re.search(
            rf"(?:geschäftsjahr|geschaeftsjahr|financial year).{{0,80}}(?:01[./-]01[./-]{year}).{{0,120}}(?:31[./-]12[./-]{year})",
            text,
            re.I | re.S,
        )
        if annual:
            return f"{year}-12-31"
    raise GlobalProviderError("official German report period end could not be verified")


def parse_german_annual_report_text(
    text: str,
    *,
    expected_year: Optional[int] = None,
) -> ParsedGermanReport:
    clean = _normalize_lines(text)
    if len(clean) < 500:
        raise GlobalProviderError("official German report text is too short")

    scope = (
        "consolidated"
        if re.search(r"konzernabschluss|konzernbilanz|consolidated financial statements|consolidated statement", clean, re.I)
        else "separate"
    )
    audited = bool(
        re.search(
            r"uneingeschränk(?:ter|ten|tes)\s+bestätigungsvermerk|"
            r"uneingeschraenk(?:ter|ten|tes)\s+bestaetigungsvermerk|"
            r"unmodified\s+(?:audit\s+)?opinion|"
            r"in our opinion.{0,240}(?:true and fair|in accordance with)",
            clean,
            re.I | re.S,
        )
    )

    fundamentals: dict[str, float] = {}
    for field in _ALIASES:
        value = _extract_field(clean, field)
        if value is not None:
            fundamentals[field] = value

    assets = fundamentals.get("total_assets")
    equity = fundamentals.get("total_equity")
    liabilities = fundamentals.get("total_liabilities")
    derived: list[str] = []
    if liabilities is None and assets is not None and equity is not None and assets >= equity:
        fundamentals["total_liabilities"] = assets - equity
        liabilities = fundamentals["total_liabilities"]
        derived.append("total_liabilities")

    if assets is None or equity is None or fundamentals.get("net_income") is None:
        raise GlobalProviderError(
            "official German report lacks strict minimum statement fields "
            "(assets, equity, net income)"
        )
    if liabilities is not None:
        gap = abs(assets - (liabilities + equity))
        scale = max(abs(assets), 1.0)
        # This gate only tolerates statement rounding; it is not an investment
        # threshold. A large accounting-identity mismatch means the parser
        # selected incompatible rows and must fail closed.
        if gap / scale > 0.002:
            raise GlobalProviderError(
                f"official German report accounting identity mismatch ({gap / scale:.4%})"
            )

    period_end = _period_end(clean, expected_year)
    return ParsedGermanReport(
        period_end=period_end,
        currency="EUR",
        report_scope=scope,
        audited=audited,
        fundamentals=fundamentals,
        derived_fields=tuple(derived),
    )
