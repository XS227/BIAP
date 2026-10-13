"""Identifier-keyed sector reference for markets whose universe carries no sector.

Nothing here runs on the request path except a local file read. A bounded sync
(``python -m global_markets.sector_reference_sync``) builds
``$BIAP_GLOBAL_DATA_DIR/sector-reference/entries.json`` keyed by ISIN, from:

* ``euronext-icb`` - the instrument's official ICB classification on Euronext Live
  (Paris, Amsterdam, Brussels, Lisbon, Milan, Oslo, Dublin);
* ``wikidata-industry`` - the ``industry`` (P452) statements of the Wikidata item
  whose ISIN (P946) equals the instrument's ISIN. An exact identifier join, never
  a name match. It is a community-curated classification, labelled as such, and
  only used where no official source is wired (Germany, Spain, Switzerland, ...).

``apply_sector_reference`` fills ``sector``/``industry`` ONLY when they are empty,
so an official universe/filing classification always wins, and records where the
value came from. It never touches a financial figure.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import re
import threading
from typing import Iterable, Optional

from .icb import ICB_INDUSTRY_NAMES, icb_industry_for_code
from .models import GlobalCompany

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict]] = {}

# --- Wikidata industry label -> ICB industry --------------------------------------

_NEGATED_INSURANCE = re.compile(r"(except|excluding|excl\.?|other than)\s+insurance", re.I)
_INSURANCE = re.compile(r"\b(re)?insurance\b|\breinsur", re.I)
_BANK = re.compile(r"\bbank(s|ing)?\b|monetary intermediation|credit institution|mortgage lend", re.I)
_FINANCE = re.compile(
    r"financial|asset management|investment|brokerage|securities|stock exchange|capital market|payment|leasing|credit",
    re.I,
)

# Ordered; first match wins. Financials are decided before this table.
_KEYWORD_INDUSTRY: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(pattern, re.I), industry)
    for pattern, industry in (
        (r"telecommunicat|mobile phone|wireless|broadband", "Telecommunications"),
        (r"software|information technology|computer|semiconductor|electronics industry|internet|data processing|it service", "Technology"),
        (r"pharmaceutical|biotechnolog|medical|health|hospital|life science|diagnostic", "Health Care"),
        (r"real estate|property|reit", "Real Estate"),
        (r"oil|natural gas|petroleum|coal|oilfield|energy industry", "Energy"),
        (r"electric(ity)? (generation|utilit|power)|water (supply|utilit)|utilit|power generation|renewable", "Utilities"),
        (r"mining|metal|steel|chemical|paper|forest|cement|plastic|fertili[sz]er|gold|aluminium|aluminum", "Basic Materials"),
        (r"food|beverage|brewing|tobacco|supermarket|grocery|agricultur|personal care|household product|cosmetic", "Consumer Staples"),
        (r"automotive|car manufactur|automobile|retail|apparel|clothing|fashion|luxury|leisure|tourism|hotel|restaurant|gaming|casino|toy|media|publishing|broadcast|entertainment|sporting|travel|airline|consumer", "Consumer Discretionary"),
        (r"aerospace|defen[cs]e|construction|engineering|machinery|transport|logistics|shipping|rail|aviation|manufactur|industrial|building|electrical equipment|waste|service", "Industrials"),
    )
)


def classify_wikidata_industries(labels: Iterable[str]) -> Optional[dict]:
    """(sector, industry, kind) from a Wikidata item's industry labels, else None.

    ``kind`` is one of insurance / bank / financial for financial institutions
    (what the agents need), else ``operating``. Ambiguous or unmapped labels
    return None - a missing sector is reported as missing, never guessed.
    """
    clean = [str(label).strip() for label in labels if str(label or "").strip()]
    if not clean:
        return None
    insurers = [label for label in clean if _INSURANCE.search(label) and not _NEGATED_INSURANCE.search(label)]
    banks = [label for label in clean if _BANK.search(label)]
    if insurers:
        return {"sector": "Financials", "industry": "Insurance", "kind": "insurance", "label": insurers[0]}
    if banks:
        return {"sector": "Financials", "industry": "Banks", "kind": "bank", "label": banks[0]}
    finance = [label for label in clean if _FINANCE.search(label)]
    if finance and len(finance) == len(clean):
        return {"sector": "Financials", "industry": "Financial Services", "kind": "financial", "label": finance[0]}
    votes: dict[str, str] = {}
    for label in clean:
        if _FINANCE.search(label):
            continue
        for pattern, industry in _KEYWORD_INDUSTRY:
            if pattern.search(label):
                votes.setdefault(industry, label)
                break
    if len(votes) == 1:
        industry, label = next(iter(votes.items()))
        return {"sector": industry, "industry": label, "kind": "operating", "label": label}
    return None


# --- store ----------------------------------------------------------------------

def reference_path(data_dir: Optional[str] = None) -> Path:
    root = data_dir or os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global"
    return Path(root) / "sector-reference" / "entries.json"


def load_entries(path: Optional[Path] = None) -> dict:
    path = path or reference_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    key = str(path)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries") if isinstance(payload, dict) else {}
        entries = entries if isinstance(entries, dict) else {}
    except (OSError, ValueError):
        entries = {}
    with _LOCK:
        _CACHE[key] = (mtime, entries)
    return entries


def save_entries(entries: dict, path: Optional[Path] = None) -> Path:
    path = path or reference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"schema": 1, "entries": entries}, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def apply_sector_reference(company: GlobalCompany, entries: Optional[dict] = None) -> GlobalCompany:
    """Fill an empty sector from the identifier-keyed reference. Never overrides."""
    if company.sector and str(company.sector).strip():
        return company
    isin = str(company.isin or "").strip().upper()
    if not isin:
        return company
    entries = load_entries() if entries is None else entries
    entry = entries.get(isin)
    if not isinstance(entry, dict):
        return company
    sector = str(entry.get("sector") or "").strip()
    if sector not in ICB_INDUSTRY_NAMES:
        return company
    fields = dict(company.raw_provider_fields or {})
    fields.update({
        "sector_source": entry.get("source"),
        "sector_kind": entry.get("kind"),
        "sector_provenance": {
            "classification": entry.get("classification"),
            "sourceUrl": entry.get("url"),
            "retrievedAt": entry.get("retrievedAt"),
            "identityCheck": "exact ISIN match",
            "code": entry.get("code"),
        },
    })
    return replace(
        company,
        sector=sector,
        industry=company.industry or (str(entry.get("industry") or "").strip() or None),
        raw_provider_fields=fields,
    )


def icb_entry(code: str, industry_label: str, sector_label: str, *, url: str, retrieved_at: str) -> Optional[dict]:
    sector = icb_industry_for_code(code)
    if not sector:
        return None
    kind = "operating"
    if sector == "Financials":
        text = f"{sector_label} {industry_label}"
        kind = "insurance" if re.search(r"insurance", text, re.I) else "bank" if re.search(r"\bbanks?\b", text, re.I) else "financial"
    return {
        "sector": sector, "industry": sector_label or industry_label, "kind": kind, "code": code,
        "source": "euronext-icb", "classification": "ICB (FTSE Russell) as published by Euronext Live",
        "url": url, "retrievedAt": retrieved_at,
    }
