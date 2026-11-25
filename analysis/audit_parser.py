"""Conservative CODAL audit-opinion parser.

The older parser classified phrases across the entire PDF text. That can create
false positives when wording such as ``به استثنای`` appears later in inventory,
notes, or other unrelated sections. This module first isolates the audit-opinion
section, then classifies only that bounded text.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional

from codal_data import CodalFiling
from codal_pdf_cache import extracted_text_for_filing

_MAX_SECTION_CHARS = 2600
_DEFAULT_WWW_BASE = "https://www.codal.ir"


def _codal_www_base() -> str:
    """Return the CODAL document host or an explicitly configured gateway."""
    return os.getenv("BIAP_CODAL_WWW_BASE", _DEFAULT_WWW_BASE).rstrip("/") + "/"


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


# A genuine section heading is a line consisting of *only* the opinion
# heading (optionally "عدم" for a disclaimer, or "مشروط"/"مردود" for a
# qualified/adverse opinion) -- never a longer sentence that merely mentions
# the word, which is common since the opinion paragraph itself repeatedly
# talks about "اظهارنظر". Anchored with ^...$ so it only matches a line
# checked in isolation (see _heading_line_offsets below), not a substring
# picked out of running prose. This also naturally excludes "مبنای
# اظهارنظر" ("Basis for Opinion"), a different, later section: that line
# starts with "مبنای", which this pattern doesn't allow.
# The canonical fairness sentence names the auditor: "این سازمان" (the state
# Audit Organization) *or* "این موسسه" / "این مؤسسه" (a private audit firm,
# by far the common case). pdftotext also routinely drops the spaces and
# ZWNJs inside it ("بهنظر", "بهنحو منصفانه نشان میدهد"), so every gap is optional.
_AUDITOR = r"(?:سازمان|م[ؤو]?سسه|شرکت\s*حسابرسی)"
_CANONICAL_RE = re.compile(r"به\s*نظر\s*این\s*" + _AUDITOR)
_FAIR_RE = re.compile(r"به\s*نحو\s*منصفانه\s*نشان\s*می\s*ده[دن]")
_EXCEPT_RE = re.compile(r"به\s*استثنای")
# Looser spellings ("به استثنا آثار", "به استثناء") only count when they sit
# inside the opinion sentence itself, i.e. before the "fairly presents" clause;
# afterwards they occur in emphasis-of-matter paragraphs that do not qualify.
_EXCEPT_LOOSE_RE = re.compile(r"به\s*استثنا")

_HEADING_LINE_RE = re.compile(r"^(?:عدم\s+)?(?:اظهارنظر|اظهار نظر)(?:\s+(?:مشروط|مردود))?\s*[:：]?$")


def _heading_line_offsets(text: str) -> tuple[str, list[int]]:
    """Normalize ``text`` line-by-line and return it with heading offsets.

    PDF-to-text extraction loses page layout, but line breaks in the raw
    text remain a real, useful signal: a heading is a short line on its own,
    while an in-sentence use of the same words sits inside a longer
    paragraph line. That signal only exists before whitespace is collapsed,
    so line boundaries have to be inspected first -- normalizing the whole
    blob at once (collapsing newlines into spaces) and then regex-scanning
    it, as the previous version of this function did, cannot tell the two
    apart and false-matches on any sentence that merely discusses the
    opinion. Lines are normalized individually and rejoined with single
    spaces so their offsets in the combined text are known exactly, rather
    than re-derived with an ambiguous substring search.
    """
    offsets: list[int] = []
    parts: list[str] = []
    cursor = 0
    for raw_line in (text or "").splitlines():
        line = _normalize_pdf_text(raw_line)
        if not line:
            continue
        if _HEADING_LINE_RE.match(line):
            offsets.append(cursor)
        parts.append(line)
        cursor += len(line) + 1  # +1 for the single space each part is joined with
    return " ".join(parts), offsets


def _extract_audit_opinion_section(text: str) -> Optional[str]:
    """Return a bounded opinion section instead of scanning the whole report.

    Preference order:
    1. the canonical ``به نظر این سازمان`` opinion sentence -- this exact
       multi-word phrase is specific enough on its own to anchor on directly;
    2. an explicit ``اظهارنظر`` / ``اظهار نظر`` heading line, only when no
       canonical sentence exists at all (true for some disclaimer wording).

    The canonical sentence is checked first, not the heading, because a real
    CODAL filing showed the heading path is not reliable: pdftotext's
    handling of bidi Persian text with numbered paragraphs can corrupt a
    heading line -- observed in production, the actual heading "مبنای
    اظهارنظر" ("Basis for Opinion") had "مبنای" silently dropped during
    extraction, leaving a bare "اظهارنظر" fragment that then got matched as
    if it were the real opinion heading and used to override a perfectly
    good canonical-sentence match found later in the same document. The
    canonical sentence has no equivalent failure mode observed so far, so it
    takes priority whenever present; the heading search is a fallback for
    when it's genuinely absent, not a preference over it.

    The section stops at common following audit-report headings and is also
    hard-capped. If no reliable anchor exists, None is returned rather than
    classifying arbitrary PDF text.
    """
    normalized, heading_offsets = _heading_line_offsets(text)
    if not normalized:
        return None

    canonical_match = _CANONICAL_RE.search(normalized)
    canonical_index = canonical_match.start() if canonical_match else -1

    # A standalone "عدم اظهار نظر" heading line is a genuine disclaimer. It must
    # win over a later "به نظر این موسسه" that belongs to another section
    # (e.g. other legal requirements), which would otherwise hide the heading.
    disclaimer_offsets = [
        o for o in heading_offsets if normalized[o:o + 3] == "عدم"
    ]

    start: Optional[int] = None
    if disclaimer_offsets:
        start = disclaimer_offsets[-1]
    elif canonical_index >= 0:
        start = canonical_index
    elif heading_offsets:
        # No canonical fairness sentence at all -- true for some disclaimer
        # wording. Prefer the *last* heading line rather than the first:
        # audit-report PDFs commonly repeat the section title in a table of
        # contents before the real section, and the real content is always
        # the later occurrence. This is only safe because heading_offsets are
        # true standalone heading lines, never an in-sentence mention.
        start = heading_offsets[-1]

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
    if "نظر مشروط" in text or _EXCEPT_RE.search(text):
        return "qualified"

    fair = _FAIR_RE.search(text)
    if fair and _EXCEPT_LOOSE_RE.search(text[: fair.start()]):
        return "qualified"

    if _CANONICAL_RE.search(text) and _FAIR_RE.search(text):
        return "unqualified"

    return None


_BASIS_HEAD = re.compile(r"مبنای\s*اظهار\s*نظر(?:\s*(?:مشروط|مردود))?")
_BASIS_STOPS = ("مسئولیت هیئت مدیره", "مسئولیت هیات مدیره", "مسئولیت حسابرس", "سایر اطلاعات", "تاکید بر مطلب خاص", "تأکید بر مطلب خاص",
                "گزارش در مورد سایر الزامات", "سایر موارد", "نظر حسابرس")
_FIRM_RE = re.compile(r"((?:م[ؤو]?سسه|سازمان)\s+حسابرسی\s+[آ-ی]+(?:\s+[آ-ی]+){0,3})")
_FIRM_STOP = re.compile(r"\s+(?:و|بر|در|به|که|این|را|است|می|گزارش|صورت|شماره|تاریخ|حسابرس|عضو|شریک|مدیر)(?:\s|$)")


def extract_audit_basis(text: str) -> Optional[str]:
    """The «مبنای اظهارنظر [مشروط]» paragraphs, verbatim, bounded; None when the heading is absent (never guessed)."""
    normalized = _normalize_pdf_text(text)
    heads = list(_BASIS_HEAD.finditer(normalized))
    for m in reversed(heads):  # the real section follows a table-of-contents mention
        body = normalized[m.end(): m.end() + 2600]
        stops = [body.find(x, 40) for x in _BASIS_STOPS]
        stops = [i for i in stops if i >= 0]
        body = (body[: min(stops)] if stops else body).strip(" :.")
        if len(body) >= 60:
            return body
    return None


def extract_auditor_name(text: str) -> Optional[str]:
    """Auditor firm named in the report (last mention = the signature block), or None."""
    normalized = _normalize_pdf_text(text)
    names = [m.group(1) for m in _FIRM_RE.finditer(normalized)]
    if not names:
        return None
    name = re.sub(r"\s+", " ", names[-1]).strip()
    head, _, tail = name.partition(" حسابرسی ")
    cut = _FIRM_STOP.search(" " + tail)
    if cut:
        tail = (" " + tail)[: cut.start()].strip()
    return f"{head} حسابرسی {tail}".strip() if tail else None


def classify_audit_opinion_from_text(text: str) -> Optional[str]:
    section = _extract_audit_opinion_section(text)
    if section is None:
        return None
    return _classify_audit_opinion_section(section)


def audit_opinion_from_pdf(filing: CodalFiling) -> Optional[str]:
    raw_text = extracted_text_for_filing(filing, www_base=_codal_www_base())
    if raw_text is None:
        return None
    return classify_audit_opinion_from_text(raw_text)


def audit_details_from_pdf(filing: CodalFiling) -> dict:
    """Auditor firm and basis-for-opinion paragraphs from the same cached PDF text as the opinion."""
    raw_text = extracted_text_for_filing(filing, www_base=_codal_www_base())
    if raw_text is None:
        return {"auditor_name": None, "audit_basis": None}
    return {"auditor_name": extract_auditor_name(raw_text), "audit_basis": extract_audit_basis(raw_text)}
