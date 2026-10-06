"""Strict statement-aware normalizer for German issuer annual reports.

The parser intentionally fails closed. It only accepts values found in the
issuer's primary consolidated income/balance/cash-flow statements (plus a small
set of explicitly named official-report metrics), anchors values to one annual
period, and validates the accounting identity before the snapshot can become
verified evidence.

It is designed for text extracted from issuer-published audited PDFs. It does
not promote vendor/search-result numbers and it never fills missing values with
estimates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Optional

from .providers import GlobalProviderError


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"[-−–]?\s*\(?\d+(?:[.,'’]\d+)*\)?")

_SECTION_MARKERS = {
    "income": (
        "konzern-gewinn- und verlustrechnung",
        "konzerngewinn- und verlustrechnung",
        "consolidated statement of income",
        "consolidated income statement",
        "consolidated statement of profit or loss",
        "consolidated profit and loss statement",
        "gewinn- und verlustrechnung",
    ),
    "balance": (
        "konzernbilanz",
        "consolidated statement of financial position",
        "consolidated balance sheet",
        "statement of financial position",
        "bilanz",
    ),
    "cashflow": (
        "konzern-kapitalflussrechnung",
        "konzernkapitalflussrechnung",
        "consolidated statement of cash flows",
        "consolidated cash flow statement",
        "statement of cash flows",
        "kapitalflussrechnung",
    ),
}

_SECTION_HINTS = {
    "income": (
        "revenue", "revenues", "sales", "umsatzerlöse", "umsatzerloese",
        "ebit", "ebitda", "net income", "profit", "earnings per share",
        "jahresüberschuss", "jahresueberschuss", "konzernergebnis",
    ),
    "balance": (
        "total assets", "summe aktiva", "bilanzsumme", "total equity",
        "eigenkapital", "current assets", "umlaufvermögen", "umlaufvermoegen",
        "current liabilities", "kurzfristige verbindlichkeiten",
        "cash and cash equivalents",
    ),
    "cashflow": (
        "cash flows from operating activities", "cash flow from operating activities",
        "cashflow aus laufender geschäftstätigkeit",
        "cashflow aus laufender geschaeftstaetigkeit",
        "cash and cash equivalents",
    ),
}

_ALIASES = {
    "revenue": (
        "umsatzerlöse", "umsatzerloese", "revenues", "revenue", "sales",
    ),
    "gross_profit": ("gross profit", "bruttoergebnis"),
    "operating_income": (
        "operating profit", "operating income", "betriebsergebnis", "ebit",
    ),
    "ebitda": ("ebitda",),
    "net_income": (
        "net income", "profit for the year", "loss for the year",
        "earnings after tax", "konzernergebnis", "jahresüberschuss",
        "jahresueberschuss", "jahresfehlbetrag", "profit",
    ),
    "total_assets": ("total assets", "summe aktiva", "bilanzsumme"),
    "total_liabilities": (
        "total liabilities", "summe schulden", "summe verbindlichkeiten",
    ),
    "total_equity": (
        "total equity", "shareholders' equity", "shareholders’ equity",
        "eigenkapital", "equity",
    ),
    "retained_earnings": (
        "retained earnings", "gewinnrücklagen", "gewinnruecklagen",
    ),
    "current_assets": ("current assets", "umlaufvermögen", "umlaufvermoegen"),
    "current_liabilities": (
        "current liabilities", "kurzfristige verbindlichkeiten",
        "kurzfristige schulden",
    ),
    "cash_and_equivalents": (
        "cash and cash equivalents",
        "zahlungsmittel und zahlungsmitteläquivalente",
        "zahlungsmittel und zahlungsmittelaequivalente",
        "liquide mittel",
    ),
    "operating_cash_flow": (
        "cash flows from operating activities",
        "cash flow from operating activities",
        "cashflow aus laufender geschäftstätigkeit",
        "cashflow aus laufender geschaeftstaetigkeit",
        "cash flow aus laufender geschäftstätigkeit",
    ),
    "interest_expense": (
        "interest and similar expenses", "interest expenses", "interest expense",
        "zinsaufwendungen",
    ),
    "eps": (
        "basic earnings per share", "diluted earnings per share",
        "earnings per share", "ergebnis je aktie",
    ),
}

_FIELD_SECTION = {
    "revenue": "income",
    "gross_profit": "income",
    "operating_income": "income",
    "ebitda": "income",
    "net_income": "income",
    "total_assets": "balance",
    "total_liabilities": "balance",
    "total_equity": "balance",
    "retained_earnings": "balance",
    "current_assets": "balance",
    "current_liabilities": "balance",
    "cash_and_equivalents": "balance",
    "operating_cash_flow": "cashflow",
    "interest_expense": "income",
    "eps": "income",
}

_DEBT_TOTAL_ALIASES = (
    "total financial liabilities", "total financial debt",
    "financial debt", "borrowings", "financial liabilities",
    "finanzverbindlichkeiten",
)
_DEBT_NONCURRENT_ALIASES = (
    "non-current financial liabilities", "non-current borrowings",
    "langfristige finanzverbindlichkeiten",
)
_DEBT_CURRENT_ALIASES = (
    "current financial liabilities", "current borrowings",
    "kurzfristige finanzverbindlichkeiten",
)
_FCF_ALIASES = ("free cash flow", "free cashflow", "freier cashflow")


@dataclass(frozen=True)
class ParsedGermanReport:
    period_end: str
    currency: str
    report_scope: str
    audited: bool
    fundamentals: dict[str, float]
    derived_fields: tuple[str, ...]


def _normalize_lines(text: str) -> str:
    lines: list[str] = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        raw = _CONTROL.sub(" ", raw)
        line = _SPACE.sub(" ", raw).strip()
        # PDF extractors often separate a Unicode minus/en-dash from the
        # numeric cell with a thin space. Rejoin only when a number follows.
        line = re.sub(r"([−–-])\s+(?=\d)", r"\1", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _parse_number(
    token: str,
    *,
    decimal_comma: Optional[bool] = None,
) -> Optional[float]:
    raw = str(token or "").strip().replace("\u2212", "-").replace("−", "-").replace("–", "-")
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")"))
    raw = raw.strip("-() ").replace("'", "").replace("’", "").replace(" ", "")
    if not raw or not any(ch.isdigit() for ch in raw):
        return None
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw:
        if decimal_comma is True:
            raw = raw.replace(",", ".")
        elif decimal_comma is False:
            raw = raw.replace(",", "")
        else:
            parts = raw.split(",")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                raw = "".join(parts)
            else:
                raw = raw.replace(",", ".")
    elif "." in raw:
        if decimal_comma is True:
            raw = raw.replace(".", "")
        elif decimal_comma is False:
            pass
        else:
            parts = raw.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                raw = "".join(parts)
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _segment_decimal_comma(segment: str) -> Optional[bool]:
    head = segment[:1200].lower()
    if any(token in head for token in ("consolidated", "statement of", "annual report")):
        return False
    if any(token in head for token in ("konzern", "bilanz", "gewinn- und verlustrechnung")):
        return True
    return None


def _multiplier_from_text(text: str) -> float:
    low = text.lower()
    patterns = (
        (
            r"(?:\bin\s+|\bangaben\s+in\s+)?(?:eur|€)\s*"
            r"(?:mio\.?|million(?:s)?|mn|m)\b|"
            r"\b(?:mio\.?|million(?:s)?|mn)\s*(?:eur|€)\b",
            1_000_000.0,
        ),
        (
            r"(?:\bin\s+|\bangaben\s+in\s+)?(?:eur|€)\s*"
            r"(?:thousand|000s?|teur|keur)\b|"
            r"\b(?:teur|keur|thousand\s+euros?)\b",
            1_000.0,
        ),
        (r"(?:\bin\s+|\bangaben\s+in\s+)(?:eur|€)\b", 1.0),
    )
    hits: list[tuple[int, float]] = []
    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, low, re.I):
            hits.append((match.start(), multiplier))
    return max(hits, default=(-1, 1.0), key=lambda row: row[0])[1]


def _explicit_multiplier(text: str) -> Optional[float]:
    low = str(text or "").lower()
    patterns = (
        (
            r"(?:\bin\s+|\bangaben\s+in\s+)?(?:eur|€)\s*"
            r"(?:mio\.?|million(?:s)?|mn|m)\b|"
            r"\b(?:mio\.?|million(?:s)?|mn)\s*(?:eur|€)\b",
            1_000_000.0,
        ),
        (
            r"(?:\bin\s+|\bangaben\s+in\s+)?(?:eur|€)\s*"
            r"(?:thousand|000s?|teur|keur)\b|"
            r"\b(?:teur|keur|thousand\s+euros?)\b",
            1_000.0,
        ),
        (r"(?:\bin\s+|\bangaben\s+in\s+)(?:eur|€)\b", 1.0),
    )
    hits: list[tuple[int, float]] = []
    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, low, re.I):
            hits.append((match.start(), multiplier))
    return max(hits, default=(-1, None), key=lambda row: row[0])[1]


def _statement_multiplier(text: str, start: int, end: int) -> float:
    # Prefer the unit declared in the statement header itself. Only if the
    # statement has no explicit unit do we inherit the nearest declaration
    # before it. Never inspect following sections (e.g. a later FCF table).
    header = text[start:min(end, start + 1000)]
    local = _explicit_multiplier(header)
    if local is not None:
        return local
    before = text[max(0, start - 1200):start]
    inherited = _explicit_multiplier(before)
    return inherited if inherited is not None else 1.0


def _nearest_multiplier(text: str, pos: int) -> float:
    # For non-statement named metrics prefer the nearest preceding unit. A
    # short forward look is intentionally avoided so later tables cannot
    # retroactively change the scale of the current metric.
    before = text[max(0, pos - 1000):pos]
    inherited = _explicit_multiplier(before)
    return inherited if inherited is not None else 1.0


def _all_section_starts(text: str) -> list[int]:
    low = text.lower()
    starts: set[int] = set()
    for markers in _SECTION_MARKERS.values():
        for marker in markers:
            cursor = 0
            while True:
                idx = low.find(marker, cursor)
                if idx < 0:
                    break
                starts.add(idx)
                cursor = idx + len(marker)
    return sorted(starts)


def _statement_windows(text: str, section: str) -> list[tuple[int, int]]:
    low = text.lower()
    starts: list[int] = []
    for marker in _SECTION_MARKERS[section]:
        cursor = 0
        while True:
            idx = low.find(marker, cursor)
            if idx < 0:
                break
            starts.append(idx)
            cursor = idx + len(marker)
    if not starts:
        return []

    every_start = _all_section_starts(text)
    ranked: list[tuple[float, int, int]] = []
    for start in sorted(set(starts)):
        later = [x for x in every_start if x > start + 80]
        end = min(later) if later else min(len(text), start + 18000)
        end = min(end, start + 18000)
        segment = text[start:end]
        segment_low = segment.lower()
        header = segment[:900].lower()

        score = 0.0
        if len(segment) >= 900:
            score += 4.0
        else:
            score -= 20.0
        if re.search(r"\b20\d{2}\b", header):
            score += 5.0
        if _multiplier_from_text(header) != 1.0 or re.search(r"\bin\s+(?:eur|€)\b", header):
            score += 6.0
        score += min(28.0, 4.0 * sum(term in segment_low for term in _SECTION_HINTS[section]))
        before = text[max(0, start - 180):start].lower()
        if "content" in before or "inhalt" in before:
            score -= 8.0
        # Real statement blocks contain many numeric cells; TOC references do not.
        score += min(10.0, len(_NUMBER.findall(segment[:6000])) / 12.0)
        ranked.append((score, start, end))

    ranked.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    return [(start, end) for _, start, end in ranked]


def _tail_starts_with_value(tail: str) -> bool:
    stripped = tail.strip()
    stripped = re.sub(r"^\(\s*in\s+(?:eur|€)\s*\)\s*", "", stripped, flags=re.I)
    # optional note reference like "(10)", "4.1", "5.10", "8.1, 8.2"
    stripped = re.sub(r"^\(?\d{1,3}(?:\.\d{1,2})?\)?(?:\s*,\s*\d+(?:\.\d+)?)?\s*", "", stripped)
    stripped = stripped.lstrip(":; ")
    if not stripped:
        return False
    return bool(re.match(r"^[−–\-(\d]", stripped))


def _row_values(
    segment: str,
    aliases: tuple[str, ...],
    *,
    field: str,
    multiplier_override: Optional[float] = None,
) -> Optional[list[float]]:
    lines = segment.split("\n")
    # The statement's own unit declaration always wins. An inherited scale is
    # only a fallback for layouts where the unit sits immediately above the
    # statement heading.
    local_multiplier = _explicit_multiplier(segment[:1200])
    block_multiplier = (
        local_multiplier
        if local_multiplier is not None
        else multiplier_override
        if multiplier_override is not None
        else 1.0
    )
    decimal_comma = _segment_decimal_comma(segment)
    for alias in aliases:
        alias_low = alias.lower()
        for idx, line in enumerate(lines):
            low = line.lower().strip()
            if field == "current_assets" and low.startswith(("non-current assets", "non current assets")):
                continue
            if field == "current_liabilities" and low.startswith(("non-current liabilities", "non current liabilities")):
                continue
            if not low.startswith(alias_low):
                continue
            tail = line[len(alias):].strip()
            if not _tail_starts_with_value(tail):
                continue
            candidate = tail
            if len(_NUMBER.findall(candidate)) < 1 and idx + 1 < len(lines):
                candidate += " " + lines[idx + 1]
            tokens = [m.group(0) for m in _NUMBER.finditer(candidate)]
            values: list[float] = []
            for token in tokens[:8]:
                value = _parse_number(token, decimal_comma=decimal_comma)
                if value is None:
                    continue
                values.append(value)
            if not values:
                continue
            # Drop a numeric note reference when it survived the textual strip.
            if len(values) >= 3 and abs(values[0]) < 100:
                values = values[1:]
            multiplier = 1.0 if field == "eps" or re.search(r"\bin\s+(?:eur|€)\b", line, re.I) else block_multiplier
            return [value * multiplier for value in values]
    return None


def _extract_field_values(text: str, field: str) -> Optional[list[float]]:
    section = _FIELD_SECTION[field]
    for start, end in _statement_windows(text, section):
        multiplier = _statement_multiplier(text, start, end)
        values = _row_values(
            text[start:end],
            _ALIASES[field],
            field=field,
            multiplier_override=multiplier,
        )
        if values:
            return values
    return None


def _extract_total_debt(text: str) -> Optional[float]:
    for start, end in _statement_windows(text, "balance"):
        segment = text[start:end]
        multiplier = _statement_multiplier(text, start, end)
        total = _row_values(
            segment, _DEBT_TOTAL_ALIASES, field="total_debt",
            multiplier_override=multiplier,
        )
        if total:
            return total[0]
        noncurrent = _row_values(
            segment, _DEBT_NONCURRENT_ALIASES, field="total_debt",
            multiplier_override=multiplier,
        )
        current = _row_values(
            segment, _DEBT_CURRENT_ALIASES, field="total_debt",
            multiplier_override=multiplier,
        )
        if noncurrent and current:
            return noncurrent[0] + current[0]
    return None


def _extract_named_metric_anywhere(text: str, aliases: tuple[str, ...]) -> Optional[float]:
    lines = text.split("\n")
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1
    for alias in aliases:
        low_alias = alias.lower()
        for idx, line in enumerate(lines):
            low = line.lower().strip()
            if not low.startswith(low_alias):
                continue
            tail = line[len(alias):].strip()
            if not _tail_starts_with_value(tail):
                continue
            values = [_parse_number(m.group(0)) for m in _NUMBER.finditer(tail)]
            values = [v for v in values if v is not None]
            if not values:
                continue
            multiplier = _nearest_multiplier(text, offsets[idx])
            return values[0] * multiplier
    return None


def _period_end(text: str, expected_year: Optional[int]) -> str:
    year = int(expected_year) if expected_year else None
    patterns = (
        re.compile(r"\b(3[01]|[12]\d|0?[1-9])\.(0?[1-9]|1[0-2])\.(20\d{2})\b"),
        re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-(3[01]|[12]\d|0[1-9])\b"),
        re.compile(r"\b(0?[1-9]|1[0-2])/(3[01]|[12]\d|0?[1-9])/(20\d{2})\b"),
    )
    dates: list[date] = []
    for pattern in patterns:
        for match in pattern.finditer(text[:50000]):
            try:
                if pattern is patterns[0]:
                    day = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                elif pattern is patterns[1]:
                    day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                else:
                    day = date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
            except ValueError:
                continue
            if year is None or day.year == year:
                dates.append(day)
    if dates:
        return max(dates).isoformat()
    if year is not None:
        annual = re.search(
            rf"(?:geschäftsjahr|geschaeftsjahr|financial year).{{0,100}}"
            rf"(?:01[./-]01[./-]{year}|01/01/{year}).{{0,160}}"
            rf"(?:31[./-]12[./-]{year}|12/31/{year})",
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
        if re.search(
            r"konzernabschluss|konzernbilanz|consolidated financial statements|"
            r"consolidated statement",
            clean,
            re.I,
        )
        else "separate"
    )
    audited = bool(
        re.search(
            r"uneingeschränk(?:ter|ten|tes)\s+bestätigungsvermerk|"
            r"uneingeschraenk(?:ter|ten|tes)\s+bestaetigungsvermerk|"
            r"unmodified\s+(?:audit\s+)?opinion|"
            r"in our opinion.{0,320}(?:true and fair|in accordance with)",
            clean,
            re.I | re.S,
        )
    )

    fundamentals: dict[str, float] = {}
    extracted: dict[str, list[float]] = {}
    for field in _ALIASES:
        values = _extract_field_values(clean, field)
        if values:
            extracted[field] = values
            fundamentals[field] = values[0]

    revenue_values = extracted.get("revenue") or []
    if len(revenue_values) > 1:
        fundamentals["revenue_prev"] = revenue_values[1]
        if revenue_values[1] != 0:
            fundamentals["revenue_yoy_pct"] = (
                revenue_values[0] / revenue_values[1] - 1.0
            ) * 100.0

    revenue = fundamentals.get("revenue")
    net_income = fundamentals.get("net_income")
    if revenue not in (None, 0) and net_income is not None:
        fundamentals["net_margin_pct"] = net_income / revenue * 100.0

    total_debt = _extract_total_debt(clean)
    if total_debt is not None:
        fundamentals["total_debt"] = total_debt

    free_cash_flow = _extract_named_metric_anywhere(clean, _FCF_ALIASES)
    if free_cash_flow is not None:
        fundamentals["free_cash_flow"] = free_cash_flow

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
