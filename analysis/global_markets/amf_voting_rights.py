"""Issued share counts from AMF "total number of voting rights and shares" notices.

French issuers must publish, every month their capital changes (Art. L.233-8 II
Code de commerce / Art. 223-16 AMF General Regulation), the total number of
shares composing the share capital and of voting rights. The notices are lodged
as regulated information with the AMF (info-financiere.gouv.fr open-data feed,
indexed by issuer ISIN/LEI) and are public, free and intended for reuse.

The PDFs are free-form: table layouts, languages and column orders differ per
issuer. The parser is therefore deliberately conservative and uses two
independent readings of the same document:

* ``labelled`` -- plain extracted text: "<number of shares ...> <number>" where
  the label is explicitly the share count (voting-rights, treasury-net and
  buy-back wordings are excluded);
* ``dated_row`` -- layout extraction: the first dated table row, whose first
  numeric cell is taken only when the column header names shares *to the left
  of* any voting-rights column.

When both fire they must agree; when only one fires its value is used; any
disagreement, image-only PDF, absent table or implausible size raises
``VotingRightsParseError`` with a reason code. Nothing is ever guessed.

Cross-checking against net income / EPS and staleness is the consumer's job
(``exchange_shares.apply_to_company``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "decembre": 12, "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_SPACE_CHARS = "    ⁠​"
MIN_SHARES = 100_000
MAX_SHARES = 50_000_000_000

# A grouped (space / comma / dot, exactly 3-digit groups) or plain integer.
_NUM_CORE = r"\d{1,3}(?:[ ,.]\d{3}){1,4}|\d{6,12}"
_NUM_AT_START = re.compile(rf"^({_NUM_CORE})(?![\d])")
_NUM_FULL = re.compile(rf"^(?:{_NUM_CORE})$")
_FOOTNOTE = re.compile(r"\s*(?:\(\s*\d\s*\)|\*+|¹|²|³)\s*$")

_SHARES_LABEL = (
    r"(?:nombre\s+(?:total\s+)?d['’]\s*actions(?:\s+(?:composant|formant|en\s+circulation)[^\d]{0,40}?)?"
    r"|nombre\s+(?:total\s+)?de\s+titres(?:\s+composant[^\d]{0,40}?)?"
    r"|total\s+number\s+of\s+(?:issued\s+)?shares(?:\s+(?:composing|forming|comprising|making\s+up)[^\d]{0,60}?)?"
    r"|number\s+of\s+shares(?:\s+(?:composing|forming|comprising|making\s+up)[^\d]{0,60}?)?"
    r"|total\s+number\s+of\s+shares)"
)
_LABELLED = re.compile(rf"{_SHARES_LABEL}\s*[:\-–]?\s*({_NUM_CORE})(?![\d])", re.I)
_BAD_CONTEXT = re.compile(
    r"vote|voting|droits|d[ée]duction|auto-?\s*d[ée]ten|autocontr|treasury|hors\s|net\s+of|exer[cç]able|"
    r"rachet|rachat|buy-?back|purchas|acquis|achet|cancel|annul",
    re.I,
)
_DATE_START = re.compile(
    rf"^(?:\d{{1,2}}(?:er)?\s+)?(?:{_MONTH_RE})\b|^(?:{_MONTH_RE})\s+\d{{1,2}}\b|"
    r"^\d{1,2}\s*[/.]|^\d{4}-\d{2}-\d{2}",
    re.I,
)
_SHARE_WORD = re.compile(r"actions|shares|titres", re.I)
_VOTE_WORD = re.compile(r"vote|voting|droits", re.I)


@dataclass(frozen=True)
class VotingRightsNotice:
    shares: int
    as_of: Optional[str]
    rule: str


class VotingRightsParseError(ValueError):
    """The notice cannot be read unambiguously; ``args[0]`` is a reason code."""


def _normalise(text: str) -> str:
    for ch in _SPACE_CHARS:
        text = text.replace(ch, " ")
    return text


def _to_int(token: str) -> Optional[int]:
    token = _FOOTNOTE.sub("", token.strip().strip(":")).strip()
    if not _NUM_FULL.match(token):
        return None
    return int(re.sub(r"[ ,.]", "", token))


def _leading_int(cell: str) -> Optional[int]:
    """Number at the start of a cell ("683337177 Nombre de droits ...")."""
    match = _NUM_AT_START.match(_FOOTNOTE.sub("", cell.strip()) if _NUM_FULL.match(_FOOTNOTE.sub("", cell.strip())) else cell.strip())
    return int(re.sub(r"[ ,.]", "", match.group(1))) if match else None


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _dates_in(text: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(rf"(\d{{1,2}})(?:er)?\s+({_MONTH_RE})\s+(20\d{{2}})", text, re.I):
        found.append(_iso(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))))
    for m in re.finditer(rf"({_MONTH_RE})\s+(\d{{1,2}}),?\s+(20\d{{2}})", text, re.I):
        found.append(_iso(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))))
    for m in re.finditer(r"(\d{2})/(\d{2})/(20\d{2})", text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        found.append(_iso(y, b, a) if a <= 31 and b <= 12 else _iso(y, a, b))
    for m in re.finditer(r"(20\d{2})-(\d{2})-(\d{2})", text):
        found.append(_iso(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return [d for d in found if d]


def _as_of(text: str, row_text: str = "") -> Optional[str]:
    """Row date if it carries a year; else the "au/as of/at" date; else latest date."""
    row = _dates_in(row_text)
    if row:
        return row[0]
    anchored = re.findall(
        rf"(?:\bau\b|\bas\s+of\b|\bat\b|date\s+du|arr[êe]t[ée]?\s+au)\s+((?:\d{{1,2}}(?:er)?\s+)?(?:{_MONTH_RE})\s+(?:\d{{1,2}},?\s+)?20\d{{2}})",
        text, re.I)
    for chunk in anchored:
        d = _dates_in(chunk)
        if d:
            return d[0]
    every = sorted(_dates_in(text))
    return every[-1] if every else None


def _cells(line: str) -> list[str]:
    cells = [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]
    merged: list[str] = []
    for cell in cells:
        # Layout extraction may split "418 344 626" at a gap ("418" | "344 626").
        if merged and re.fullmatch(r"\d{1,3}", merged[-1]) and re.fullmatch(r"\d{3}(?:[ ,.]\d{3})*", _FOOTNOTE.sub("", cell)):
            merged[-1] = f"{merged[-1]} {cell}"
        else:
            merged.append(cell)
    return merged


def _labelled(plain: str) -> Optional[tuple[int, str]]:
    flat = re.sub(r"\s+", " ", _normalise(plain))
    hits: list[int] = []
    for m in _LABELLED.finditer(flat):
        whole = m.group(0)
        if _BAD_CONTEXT.search(whole):
            continue
        # The sentence just before must not be a buy-back/treasury statement.
        value = int(re.sub(r"[ ,.]", "", m.group(1)))
        if value >= MIN_SHARES:
            hits.append(value)
    if not hits:
        return None
    distinct = sorted(set(hits))
    if len(distinct) > 1:
        # Several labelled counts (e.g. a table of months): the first is the
        # current one in every observed issuer layout, but only accept when all
        # candidates are the same number or the first is the largest-date row.
        return hits[0], "labelled"
    return distinct[0], "labelled"


def _header_block(raw: list[str], at: int) -> list[str]:
    """Column-header lines directly above raw line ``at`` (prose/titles excluded).

    Walks upwards over table-like lines (internal column gaps, a deep indent or
    a few words), skips value lines (a >= 6 digit number), and stops at the
    first prose line or at a blank-line break once a header line was seen.
    """
    block: list[str] = []
    blanks = 0
    for back in range(at - 1, max(-1, at - 30), -1):
        cand = raw[back]
        if not cand.strip():
            blanks += 1
            if blanks >= 2 and block:
                break
            continue
        blanks = 0
        text = cand.strip()
        if re.search(r"\d{1,3}(?:[ ,.]\d{3}){2}|\d{7,}", text):
            continue  # a value line interleaved with the header (e.g. votes row)
        indent = len(cand) - len(cand.lstrip())
        if re.search(r"\S\s{3,}\S", text) or indent >= 8 or len(text.split()) <= 5:
            block.append(cand)
        else:
            break
    return block


def _dated_row(layout: str) -> Optional[tuple[int, str, Optional[str]]]:
    raw = _normalise(layout).splitlines()
    nonblank = [i for i, ln in enumerate(raw) if ln.strip()]
    for pos, idx in enumerate(nonblank[:140]):
        cells = _cells(raw[idx])
        if not cells:
            continue
        first = cells[0]
        # Date split over two lines: "September 30," / "2026  295,722,284"
        prefix = ""
        prev = raw[nonblank[pos - 1]].strip() if pos > 0 else ""
        if re.fullmatch(r"20\d{2}", first) and re.search(rf"({_MONTH_RE})\s+\d{{1,2}},?\s*$", prev, re.I):
            prefix = prev + " "
        elif not _DATE_START.match(first):
            continue
        values: list[int] = []
        for cell in cells[1:]:
            v = _to_int(cell) or _leading_int(cell)
            if v is not None and v >= MIN_SHARES:
                values.append(v)
        if not values and len(cells) == 1:
            tail = re.sub(rf"^(?:\d{{1,2}}(?:er)?\s+)?(?:{_MONTH_RE}\s+)?(?:\d{{1,2}},?\s+)?(?:20\d{{2}}|\d{{2}}/\d{{2}}/\d{{4}})\s*", "", first)
            v = _leading_int(tail) if tail != first else None
            if v and v >= MIN_SHARES:
                values.append(v)
        if not values:
            continue
        block = _header_block(raw, nonblank[pos - 1] if prefix else idx)
        block = [b for b in block if not (_dates_in(b) and not _SHARE_WORD.search(b))]
        share_x = min((m.start() for b in block for m in [_SHARE_WORD.search(b)] if m), default=None)
        vote_x = min((m.start() for b in block for m in [_VOTE_WORD.search(b)] if m), default=None)
        if share_x is None:
            continue
        if vote_x is not None and share_x > vote_x + 2:
            continue
        return values[0], "dated_row", _as_of("", prefix + " ".join(cells[:2]))
    return None


def parse_voting_rights_notice(plain: str, layout: Optional[str] = None) -> VotingRightsNotice:
    """Read the total number of shares composing the capital from notice text."""
    layout = layout if layout is not None else plain
    joined = (plain or "") + "\n" + (layout or "")
    if len(re.sub(r"\s+", "", joined)) < 80:
        raise VotingRightsParseError("no_text_layer")
    head = _normalise(joined)[:6000]
    if not re.search(r"droits?\s+de\s+vote|voting\s+rights", head, re.I):
        raise VotingRightsParseError("not_a_voting_rights_notice")

    results: list[tuple[int, str, Optional[str]]] = []
    # Plain extraction can detach a number from its label (ABC arbitrage);
    # the layout extraction keeps label and value on one row, so it is the
    # second reading of the same label rule.
    labelled = _labelled(plain or layout) or (_labelled(layout) if layout and layout is not plain else None)
    if labelled:
        results.append((labelled[0], "labelled", None))
    row = _dated_row(layout)
    if row:
        results.append(row)
    values = {r[0] for r in results}
    if not values:
        raise VotingRightsParseError("no_share_count_found")
    if len(values) > 1:
        raise VotingRightsParseError(f"conflicting_counts:{sorted(values)}")
    shares = next(iter(values))
    if not MIN_SHARES <= shares <= MAX_SHARES:
        raise VotingRightsParseError(f"implausible_count:{shares}")
    row_date = row[2] if row else None
    return VotingRightsNotice(
        shares=shares,
        as_of=row_date or _as_of(head),
        rule="+".join(sorted({r[1] for r in results})),
    )


# --- retrieval --------------------------------------------------------------
FEED_URL = "https://www.info-financiere.gouv.fr/api/explore/v2.1/catalog/datasets/flux-amf-new-prod/records"
FILE_BASE = "https://fr.ftp.opendatasoft.com/datadila/INFOFI/"
_TITLE_OK = re.compile(r"droits?\s+de\s+vote|voting\s+rights", re.I)
_TITLE_BAD = re.compile(r"transactions?|actions\s+propres|rachat|buy-?back|liquidity|liquidit|contrat", re.I)
MAX_NOTICE_AGE_DAYS = 400
MAX_PDF_FETCHES = 6


def candidate_notices(rows: list[dict]) -> list[dict]:
    """Keep feed rows whose title names voting rights and is not a buy-back report."""
    kept = []
    for row in rows:
        title = str(row.get("informationdeposee_inf_tit_inf") or "")
        name = str(row.get("fichierdecontenu_inf_fic_nom") or "")
        if not name.lower().endswith(".pdf"):
            continue
        # Short generic titles ("droits de vote") are common; the PDF is the judge.
        if _TITLE_BAD.search(title):
            continue
        if _TITLE_OK.search(title) or len(title) < 30:
            kept.append(row)
    return kept


def fetch_latest_notice(session, isin: str, *, today: Optional[date] = None, pdf_text=None) -> tuple[Optional[dict], str]:
    """Return ``(entry, status)`` for the newest parseable notice of one ISIN.

    ``pdf_text(bytes) -> (plain, layout)`` is injectable for tests.
    """
    today = today or date.today()
    params = {
        # Issuers file these under several subtypes (006000, 001006, ...), so
        # the title is the selector rather than the subtype.
        "where": (f'identificationsociete_iso_cd_isi="{isin}" and '
                  '(search(informationdeposee_inf_tit_inf,"droits de vote") or '
                  'search(informationdeposee_inf_tit_inf,"voting rights"))'),
        "order_by": "informationdeposee_inf_dat_emt desc",
        "select": "informationdeposee_inf_dat_emt,informationdeposee_inf_tit_inf,fichierdecontenu_inf_fic_nom,uin_idt_uin",
        "limit": 40,
    }
    response = session.get(FEED_URL, params=params, headers={"Accept": "application/json"}, timeout=30)
    response.raise_for_status()
    rows = candidate_notices(response.json().get("results") or [])
    if not rows:
        return None, "no_notice_in_feed"
    last_error = "no_notice_in_feed"
    for row in rows[:MAX_PDF_FETCHES]:
        url = FILE_BASE + str(row["fichierdecontenu_inf_fic_nom"]).lstrip("/")
        try:
            pdf = session.get(url, timeout=40)
            pdf.raise_for_status()
            plain, layout = (pdf_text or pdf_to_text)(pdf.content)
            notice = parse_voting_rights_notice(plain, layout)
        except VotingRightsParseError as exc:
            last_error = f"parse:{exc.args[0]}"
            continue
        except Exception as exc:  # noqa: BLE001 - network/PDF failure, recorded
            last_error = f"fetch:{type(exc).__name__}"
            continue
        anchor = notice.as_of or str(row.get("informationdeposee_inf_dat_emt") or "")[:10]
        try:
            age = (today - date.fromisoformat(anchor)).days
        except ValueError:
            return None, "undated_notice"
        if age > MAX_NOTICE_AGE_DAYS:
            return None, f"stale_notice_{age}d"
        return {
            "shares": float(notice.shares), "as_of": anchor, "rule": notice.rule,
            "published_at": row.get("informationdeposee_inf_dat_emt"),
            "notice_id": row.get("uin_idt_uin"), "source_url": url,
        }, "ok"
    return None, last_error


def pdf_to_text(content: bytes) -> tuple[str, str]:
    """Plain and layout text via poppler's ``pdftotext`` (no shell, bytes on stdin)."""
    import subprocess
    out = []
    for flags in ([], ["-layout"]):
        proc = subprocess.run(["pdftotext", *flags, "-", "-"], input=content, capture_output=True, timeout=30, check=False)
        out.append(proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else "")
    return out[0], out[1]
