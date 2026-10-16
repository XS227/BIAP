"""US ISIN resolution from open, authoritative identifier sources only.

Chain (no CUSIP licence needed, nothing persisted):
  1. GLEIF (open data, CC0): issuer legal name -> LEI -> ISINs mapped to that LEI.
  2. OpenFIGI (open FIGI standard): ISIN -> FIGI record. An ISIN is accepted only
     when the FIGI record is an Equity whose ticker equals the company's ticker
     and whose name matches the issuer.
The restricted CUSIP/13(f) datasets are deliberately NOT used. Anything that
cannot be verified stays None: a missing ISIN never blocks the analysis, it is
only an identifier (see ``enrich_with_us_isin``).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import replace
from functools import lru_cache
from typing import Callable, Optional

GLEIF = "https://api.gleif.org/api/v1"
OPENFIGI = "https://api.openfigi.com/v3/mapping"
PROVENANCE = "gleif-lei-isin+openfigi-ticker-match"

_STOP = frozenset(
    "INC CORP CORPORATION CO COS COMPANY COMPANIES LTD LIMITED PLC HOLDINGS HOLDING HLDGS HLDG THE NEW DEL NV N V SA AG "
    "GROUP COM COMMON STOCK ORDINARY SHARES CLASS CL A B C AND CAP STK DE LLC LP".split()
)
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def is_valid_isin(value: str) -> bool:
    """ISO 6166 structure + Luhn check digit (public standard, no dataset involved)."""
    value = (value or "").strip().upper()
    if not _ISIN_RE.match(value):
        return False
    digits = "".join(str(int(ch, 36)) for ch in value)
    total = 0
    for index, ch in enumerate(reversed(digits)):
        number = int(ch)
        if index % 2 == 1:
            number *= 2
            number = number // 10 + number % 10
        total += number
    return total % 10 == 0


def issuer_tokens(name: str) -> list[str]:
    text = re.sub(r"\(.*?\)", "", (name or "").upper())
    text = re.sub(r"\s+-\s+.*$", "", text)
    text = re.sub(r"[.,\-&/']", " ", text)
    return [t for t in text.split() if t not in _STOP]


def _same_issuer(a: str, b: str) -> bool:
    ta, tb = issuer_tokens(a), issuer_tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(x == y or x.startswith(y) or y.startswith(x) for y in long_) for x in short)


def _norm_ticker(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _equity_like(isin: str) -> bool:
    """Ordering heuristic only (verification is the FIGI match): US equity issue digits are numeric."""
    return isin.startswith("US") and len(isin) == 12 and isin[8:10].isdigit()


class Http:
    """Injected so tests never touch the network; production uses requests with a hard timeout."""

    def __init__(self, timeout: float = 15.0) -> None:
        import requests

        self._s = requests.Session()
        self._s.headers["User-Agent"] = "BIAP-Global/1.0 isin-resolver"
        self.timeout = timeout

    def get(self, url: str, params: Optional[dict] = None) -> dict:
        r = self._s.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def post(self, url: str, payload: list) -> list:
        r = self._s.post(url, json=payload, timeout=self.timeout)
        if r.status_code == 429:  # OpenFIGI unauthenticated limit: wait once, then give up (never guess)
            time.sleep(min(float(r.headers.get("Retry-After", "6") or 6), 12.0))
            r = self._s.post(url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()


def resolve_us_isin(
    ticker: str,
    name: str,
    *,
    http=None,
    max_lei_candidates: int = 4,
    max_isin_pages: int = 5,
    max_figi_batches: int = 4,
) -> Optional[dict]:
    """``{"isin","lei","figi","provenance"}`` when verified, else None (never a guess)."""
    http = http or Http()
    want = _norm_ticker(ticker)
    if not want or not issuer_tokens(name):
        return None
    leis: list[tuple[str, str]] = []
    base_name = re.sub(r"\s+-\s+.*$", "", name or "").strip()
    base_name = re.sub(
        r"\s+(common stock|ordinary shares?|class [a-c].*|american depositary.*|new york registry shares|capital stock)$",
        "", re.sub(r"\s*\(the\)", "", base_name, flags=re.I), flags=re.I,
    ).strip()
    for params in (
        {"filter[entity.legalName]": base_name, "filter[entity.legalAddress.country]": "US", "page[size]": 5},
        {"filter[fulltext]": " ".join(issuer_tokens(name)[:3]), "filter[entity.legalAddress.country]": "US", "page[size]": 25},
        # US-listed foreign issuers (ADR / NY registry shares): same exact-name lookup without the domicile filter.
        {"filter[entity.legalName]": base_name, "page[size]": 5},
    ):
        try:
            data = http.get(f"{GLEIF}/lei-records", params).get("data") or []
        except Exception:
            continue
        for row in data:
            legal = (((row.get("attributes") or {}).get("entity") or {}).get("legalName") or {}).get("name") or ""
            if row.get("id") and _same_issuer(legal, name) and (row["id"], legal) not in leis:
                leis.append((row["id"], legal))
        if any(issuer_tokens(legal) == issuer_tokens(name) for _, legal in leis):
            break  # an exact issuer-name record was found; otherwise keep widening the search
    want_tokens = issuer_tokens(name)
    leis.sort(key=lambda item: issuer_tokens(item[1]) != want_tokens)  # exact issuer name first
    for lei, legal in leis[:max_lei_candidates]:
        candidates: list[str] = []
        for page in range(1, max_isin_pages + 1):
            try:
                payload = http.get(f"{GLEIF}/lei-records/{lei}/isins", {"page[size]": 200, "page[number]": page})
            except Exception:
                break
            for row in payload.get("data") or []:
                isin = str(((row.get("attributes") or {}).get("isin")) or "").upper()
                if is_valid_isin(isin) and isin not in candidates:
                    candidates.append(isin)
            last = ((payload.get("meta") or {}).get("pagination") or {}).get("lastPage") or 1
            if page >= int(last):
                break
        ordered = (
            [i for i in candidates if _equity_like(i)]
            + [i for i in candidates if not _equity_like(i) and i.startswith("US")]
            + [i for i in candidates if not i.startswith("US")]
        )
        for start in range(0, min(len(ordered), 10 * max_figi_batches), 10):
            batch = ordered[start:start + 10]
            try:
                reply = http.post(OPENFIGI, [{"idType": "ID_ISIN", "idValue": i} for i in batch])
            except Exception:
                break
            for isin, item in zip(batch, reply):
                for rec in (item or {}).get("data") or []:
                    if (
                        rec.get("marketSector") == "Equity"
                        and _norm_ticker(rec.get("ticker", "")) == want
                        and _same_issuer(rec.get("name", ""), name)
                    ):
                        return {"isin": isin, "lei": lei, "figi": rec.get("figi"), "provenance": PROVENANCE}
    return None


@lru_cache(maxsize=2048)
def _cached(ticker: str, name: str) -> Optional[tuple]:
    found = resolve_us_isin(ticker, name)
    return (found["isin"], found["lei"], found["figi"]) if found else None


def enrich_with_us_isin(company, *, deadline_sec: float = 20.0):
    """Best-effort ISIN/LEI enrichment. Disabled unless BIAP_GLOBAL_US_ISIN_RESOLVE=1.

    Never raises and never changes any analytical field: on any failure the
    company is returned unchanged and analysis continues with ``isin=None``.
    """
    if os.environ.get("BIAP_GLOBAL_US_ISIN_RESOLVE") != "1":
        return company
    if getattr(company, "country", "").upper() != "US" or getattr(company, "isin", None):
        return company
    started = time.monotonic()
    try:
        found = _cached(company.ticker, company.name)
    except Exception:
        return company
    if not found or time.monotonic() - started > deadline_sec:
        return company
    isin, lei, figi = found
    raw = dict(company.raw_provider_fields or {})
    raw["isin_resolution"] = {"isin": isin, "lei": lei, "figi": figi, "provenance": PROVENANCE}
    return replace(company, isin=isin, lei=company.lei or lei, raw_provider_fields=raw)
