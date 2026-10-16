"""US ISIN resolution from authoritative identifiers (SEC 13(f) list + GLEIF).

ISIN = country prefix + 9-character CUSIP + ISO 6166 check digit. The CUSIP
comes from the SEC "Official List of Section 13(f) Securities"; a candidate is
only accepted when the issuer name matches uniquely AND GLEIF returns a LEI
record for the derived ISIN whose legal name matches. Anything else stays
unresolved (None): identity is never guessed.

Pure functions only: no download, no persistence. CUSIP data is licensed by CGS
("no redistribution"), so callers must not publish the derived mapping in bulk.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

_STOP = frozenset(
    "INC CORP CORPORATION CO COS COMPANY COMPANIES LTD PLC HOLDINGS HLDGS HLDG HOLDING THE NEW DEL NV N V SA AG "
    "GROUP COM COMMON STOCK ORDINARY SHARES CLASS CL A B C AND CAP STK DE LLC LP REGISTRY YORK".split()
)
_SKIP_TITLES = ("CALL", "PUT", "NOTE", "WT", "WARR", "*")


def isin_from_cusip(cusip: str, prefix: str = "US") -> Optional[str]:
    cusip = (cusip or "").strip().upper()
    if len(cusip) != 9 or not re.fullmatch(r"[0-9A-Z*@#]{9}", cusip) or not re.fullmatch(r"[A-Z]{2}", prefix):
        return None
    digits = "".join(str(int(ch, 36)) for ch in prefix + cusip if ch.isalnum())
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 0:
            value *= 2
            value = value // 10 + value % 10
        total += value
    return f"{prefix}{cusip}{(10 - total % 10) % 10}"


def issuer_tokens(name: str) -> list[str]:
    text = re.sub(r"\(.*?\)", "", (name or "").upper())
    text = re.sub(r"\s+-\s+.*$", "", text)
    text = re.sub(r"[.,\-&]", " ", text)
    return [t for t in text.split() if t not in _STOP]


def _same_issuer(a: list[str], b: list[str]) -> bool:
    return bool(a) and len(a) == len(b) and all(x == y or x.startswith(y) or y.startswith(x) for x, y in zip(a, b))


def match_13f_rows(name: str, rows: Iterable[tuple[str, str, str]], share_class: Optional[str] = None) -> list[tuple[str, str, str]]:
    """Rows are ``(cusip9, issuer_name, title)``. Exact token match wins over abbreviation match."""
    query = issuer_tokens(name)
    usable = [r for r in rows if r[2].split()[:1] and r[2].split()[0] not in _SKIP_TITLES and not r[2].startswith(_SKIP_TITLES)]
    exact = [r for r in usable if issuer_tokens(r[1]) == query]
    found = exact or [r for r in usable if _same_issuer(query, issuer_tokens(r[1]))]
    if share_class:
        found = [r for r in found if re.search(rf"\bCL {re.escape(share_class)}\b", r[2])]
    elif len(found) > 1:
        common = [r for r in found if r[2].split()[0] in {"COM", "CL", "SHS", "ADR", "ADS", "SPONSORED", "CAP", "N"}]
        found = common or found
    return found


def resolve_us_isin(name: str, rows: Iterable[tuple[str, str, str]], *, share_class: Optional[str] = None) -> Optional[str]:
    """Candidate ISIN when the 13(f) match is unique; caller must still verify it against GLEIF."""
    found = match_13f_rows(name, rows, share_class)
    if len(found) != 1:
        return None
    cusip = found[0][0]
    return isin_from_cusip(cusip)
