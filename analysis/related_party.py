"""Conservative related-party risk parser for audited CODAL PDFs.

The parser only raises flags for explicit warning language near related-party
context. Routine disclosure of related-party transactions is not itself treated
as a risk flag. Missing or ambiguous evidence stays ``None``.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional

from codal_data import CodalFiling
from codal_pdf_cache import extracted_text_for_filing

_DEFAULT_WWW_BASE = "https://www.codal.ir"


def _codal_www_base() -> str:
    """Return the CODAL document host or an explicitly configured gateway."""
    return os.getenv("BIAP_CODAL_WWW_BASE", _DEFAULT_WWW_BASE).rstrip("/") + "/"


def _normalize_pdf_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(
        ch for ch in normalized
        if unicodedata.category(ch) != "Cf"
    )
    normalized = normalized.translate(str.maketrans({
        "ھ": "ه",
        "ۀ": "ه",
        "ة": "ه",
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "\u200c": " ",
    }))
    return re.sub(r"\s+", " ", normalized).strip()


def _related_party_windows(text: str, radius: int = 700) -> list[str]:
    normalized = _normalize_pdf_text(text)
    if not normalized:
        return []

    anchors = (
        "اشخاص وابسته",
        "طرفهای وابسته",
        "طرف های وابسته",
        "معاملات با اشخاص وابسته",
        "ماده 129",
        "ماده ۱۲۹",
    )
    windows: list[str] = []
    for anchor in anchors:
        start = 0
        while True:
            idx = normalized.find(anchor, start)
            if idx < 0:
                break
            left = max(0, idx - radius)
            right = min(len(normalized), idx + len(anchor) + radius)
            windows.append(normalized[left:right])
            start = idx + len(anchor)
    return windows


_WARNING_PATTERNS = (
    # Corporate-law / board-approval concerns.
    r"(?:عدم\s+رعایت.{0,100}ماده\s*[۱۲1][۲2][۹9]|ماده\s*[۱۲1][۲2][۹9].{0,100}(?:عدم\s+رعایت|رعایت\s+نشده))",
    r"(?:عدم|بدون)\s+(?:اخذ\s+)?مجوز.{0,100}(?:هیئت|هیات)\s*مدیره",
    # Disclosure concerns.
    r"(?:عدم\s+افشا|افشا\s+نشده|افشای\s+ناکافی|افشا\s+به\s+طور\s+کامل\s+انجام\s+نشده)",
    # Explicitly abnormal/non-ordinary transaction terms.
    r"(?:خارج\s+از\s+(?:روال|شرایط)\s+عادی|شرایط\s+غیرمتعارف|شرایط\s+غیر\s+متعارف)",
    # Explicit non-compliance with the related-party disclosure standard.
    r"(?:عدم\s+رعایت.{0,100}استاندارد\s+حسابداری.{0,40}(?:12|۱۲)|استاندارد\s+حسابداری.{0,40}(?:12|۱۲).{0,100}رعایت\s+نشده)",
)


def _related_party_flags_from_text(text: str) -> Optional[int]:
    """Return explicit related-party red-flag count, 0, or None.

    ``None`` means no related-party context could be verified in the extracted
    text. ``0`` means the report contains related-party context but none of the
    explicit warning patterns below. Positive values count distinct warning
    categories, not raw phrase occurrences.
    """
    windows = _related_party_windows(text)
    if not windows:
        return None

    # Each pattern is checked against every window independently, never
    # against the windows joined together. Two mentions of "اشخاص وابسته"
    # can be a thousand+ characters apart in the source document; joining
    # their windows with a bare space would let the tail of one window and
    # the head of another read as a single sentence and trigger a proximity
    # pattern (e.g. "...ماده 129" from one location right next to "رعایت
    # نشده" from a wholly unrelated one) that never actually appears
    # together in the real document.
    flags = 0
    for pattern in _WARNING_PATTERNS:
        if any(re.search(pattern, window) for window in windows):
            flags += 1

    return flags


def related_party_flags_from_pdf(filing: CodalFiling) -> Optional[int]:
    text = extracted_text_for_filing(filing, www_base=_codal_www_base())
    if text is None:
        return None
    return _related_party_flags_from_text(text)
