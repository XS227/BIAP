"""Strict SEC issuer identity for non-US listings (cross-listed filers).

The SEC filer name carries header artefacts ("BANK OF MONTREAL /CAN/",
"CANADIAN PACIFIC KANSAS CITY LTD/CN") and local catalogs sometimes show only
an abbreviation ("TD") or a reversed article ("Bank of Nova Scotia (The)").
Identity is still exact on the legal-name core; this module only removes those
formatting artefacts, adds the issuer's GLEIF legal name (via its ISIN) as a
candidate, and can resolve the CIK from the SEC filer title when the local
ticker belongs to a different US company (TSX "CNR" vs Core Natural Resources).
A name-based CIK is accepted only when exactly one SEC filer matches.
"""
from __future__ import annotations

import re
import threading
from typing import Iterable, Optional

from .gleif import GLEIFResolver, _legal_core
from .models import GlobalCompany
from .providers import GlobalProviderError

_SEC_SUFFIX = re.compile(r"\s*[/\\]\s*[A-Z]{2,4}\s*[/\\]?\s*$")  # "/CAN/", "/CN", "\BC\"
_ARTICLE_SUFFIX = re.compile(r"\s*\(\s*the\s*\)\s*$", re.I)  # "Bank of Nova Scotia (The)"
_ARTICLE_PREFIX = re.compile(r"^\s*the\s+", re.I)

_titles_lock = threading.Lock()
_titles: Optional[dict[str, set[int]]] = None
_gleif_names: dict[str, Optional[str]] = {}


def sec_core(name: str) -> str:
    text = str(name or "").strip()
    previous = None
    while text != previous:
        previous = text
        text = _SEC_SUFFIX.sub("", text)
        text = _ARTICLE_SUFFIX.sub("", text)
        text = _ARTICLE_PREFIX.sub("", text)
    return _legal_core(text)


def gleif_legal_name(company: GlobalCompany) -> Optional[str]:
    isin = (company.isin or "").strip().upper()
    if len(isin) != 12:
        return None
    if isin not in _gleif_names:
        try:
            _gleif_names[isin] = GLEIFResolver().resolve_isin(isin).legal_name
        except GlobalProviderError:
            _gleif_names[isin] = None
    return _gleif_names[isin]


class IssuerNames:
    """Catalog/issuer names, extended lazily with the GLEIF legal name."""

    def __init__(self, company: GlobalCompany, extra: Iterable[str] = ()) -> None:
        self.company = company
        self.local = [n for n in dict.fromkeys(str(x or "").strip() for x in (company.name, *extra)) if n]
        self._with_gleif: Optional[list[str]] = None

    def all(self) -> list[str]:
        if self._with_gleif is None:
            legal = gleif_legal_name(self.company)
            self._with_gleif = self.local + ([legal] if legal and legal not in self.local else [])
        return self._with_gleif

    def matches(self, entity_name: str) -> bool:
        return _matches(entity_name, self.local) or _matches(entity_name, self.all())


def issuer_names(company: GlobalCompany, extra: Iterable[str] = ()) -> IssuerNames:
    return IssuerNames(company, extra)


def _matches(entity_name: str, names: Iterable[str]) -> bool:
    entity = sec_core(entity_name)
    return bool(entity) and any(sec_core(name) == entity for name in names if sec_core(name))


def identity_matches(entity_name: str, names) -> bool:
    if isinstance(names, IssuerNames):
        return names.matches(entity_name)
    return _matches(entity_name, names)


def cik_by_name(provider, names: Iterable[str]) -> Optional[int]:
    """The unique SEC filer CIK whose title core equals one issuer name core."""
    global _titles
    if _titles is None:
        with _titles_lock:
            if _titles is None:
                from .sec_edgar import SEC_TICKERS_URL

                payload = provider._get_json(SEC_TICKERS_URL)
                index: dict[str, set[int]] = {}
                for row in payload.values():
                    if isinstance(row, dict) and row.get("title") and row.get("cik_str") is not None:
                        index.setdefault(sec_core(str(row["title"])), set()).add(int(row["cik_str"]))
                _titles = index
    matches: set[int] = set()
    for name in (names.all() if isinstance(names, IssuerNames) else names):
        core = sec_core(name)
        if core:
            matches |= _titles.get(core, set())
    return next(iter(matches)) if len(matches) == 1 else None
