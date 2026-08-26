"""Conservative CODAL audit-opinion parser.

The older parser classified phrases across the entire PDF text. That can create
false positives when wording such as ``به استثنای`` appears later in inventory,
notes, or other unrelated sections. This module first isolates the audit-opinion
section, then classifies only that bounded text.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unicodedata
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from codal_data import CodalFiling

_TIMEOUT = 8
_MAX_SECTION_CHARS = 2600


def _normalize_pdf_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
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
        "\u200f": " ",
        "\u200e": " ",
    }))
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_audit_opinion_section(text: str) -> Optional[str]:
    """Return a bounded opinion section instead of scanning the whole report.

    Preference order:
    1. explicit ``اظهارنظر`` / ``اظهار نظر`` heading;
    2. the canonical ``به نظر این سازمان`` opinion sentence.

    The section stops at common following audit-report headings and is also
    hard-capped. If no reliable anchor exists, None is returned rather than
    classifying arbitrary PDF text.
    """
    normalized = _normalize_pdf_text(text)
    if not normalized:
        return None

    heading_matches = list(re.finditer(r"(?:^|\s)(اظهارنظر|اظهار نظر)(?:\s|[:：])", normalized))
    canonical_index = normalized.find("به نظر این سازمان")

    start: Optional[int] = None
    if heading_matches:
        # Prefer the heading nearest before the canonical opinion sentence when
        # present; otherwise use the first explicit opinion heading.
        if canonical_index >= 0:
            prior = [m for m in heading_matches if m.start() <= canonical_index]
            match = prior[-1] if prior else heading_matches[0]
        else:
            match = heading_matches[0]
        start = match.start()
    elif canonical_index >= 0:
        start = canonical_index

    if start is None:
        return None

    window = normalized[start : start + _MAX_SECTION_CHARS]
    stop_markers = (
        "مبنای اظهارنظر",
        "مبنای اظهار نظر",
        "تاکید بر مطلب خاص",
        "تأکید بر مطلب خاص",
        "سایر اطلاعات",
        "مسئولیت هیئت مدیره",
        "مسئولیت هیات مدیره",
        "مسئولیت حسابرس",
        "گزارش در مورد سایر الزامات قانونی",
    )

    stop_positions = []
    for marker in stop_markers:
        pos = window.find(marker, 80)
        if pos >= 0:
            stop_positions.append(pos)

    if stop_positions:
        window = window[: min(stop_positions)]

    section = window.strip()
    return section if len(section) >= 40 else None


def _classify_audit_opinion_section(section: str) -> Optional[str]:
    text = _normalize_pdf_text(section)
    if not text:
        return None

    if "عدم اظهارنظر" in text or "عدم اظهار نظر" in text:
        return "disclaimer"

    if "نظر مردود" in text or "اظهارنظر مردود" in text or "اظهار نظر مردود" in text:
        return "adverse"

    # Qualified wording must be evaluated before the clean opinion because some
    # qualified reports can still contain otherwise standard opinion language.
    if "نظر مشروط" in text or "به استثنای" in text:
        return "qualified"

    if (
        "به نظر این سازمان" in text
        and (
            "به نحو منصفانه نشان می دهد" in text
            or "به نحو منصفانه نشان میدهد" in text
        )
    ):
        return "unqualified"

    return None


def classify_audit_opinion_from_text(text: str) -> Optional[str]:
    section = _extract_audit_opinion_section(text)
    if section is None:
        return None
    return _classify_audit_opinion_section(section)


def audit_opinion_from_pdf(filing: CodalFiling) -> Optional[str]:
    if not filing.pdf_url:
        return None

    pdf_url = urljoin("https://www.codal.ir/", filing.pdf_url)
    req = Request(pdf_url, headers={"User-Agent": "Mozilla/5.0 BIAP/1.0"})

    try:
        with urlopen(req, timeout=_TIMEOUT) as response:
            pdf_bytes = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "audit.pdf")
            txt_path = os.path.join(tmpdir, "audit.txt")

            with open(pdf_path, "wb") as handle:
                handle.write(pdf_bytes)

            subprocess.run(
                ["pdftotext", "-layout", pdf_path, txt_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )

            with open(txt_path, "r", encoding="utf-8", errors="ignore") as handle:
                raw_text = handle.read()
    except (OSError, subprocess.SubprocessError):
        return None

    return classify_audit_opinion_from_text(raw_text)
