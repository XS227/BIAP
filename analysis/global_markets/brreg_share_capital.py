"""Issued share counts of Norwegian companies from the Brønnøysund register.

Enhetsregisteret (data.brreg.no, open data under NLOD) publishes each limited
company's registered share capital with the number of shares
(``kapital.antallAksjer``) and the date the entry was registered
(``innfortDato``). Oslo Børs / Euronext Live exposes no share count, so this is
the official source for the P/B gap of Norwegian listings.

Identity is never matched by name. The issuer's ISIN is resolved to its LEI
record through GLEIF; the record's ``registeredAs`` under registration
authority ``RA000472`` / ``RA000473`` (Enhetsregisteret) is the organisation number. Anything
else (a foreign registry, several LEIs, a non-share or non-NOK capital) is
refused with a reason code. The registered count is the *issued* count
(treasury shares included); the consumer cross-checks it against net income /
EPS before use (``exchange_shares.apply_to_company``).
"""
from __future__ import annotations

import re
from typing import Optional

GLEIF_URL = "https://api.gleif.org/api/v1/lei-records"
BRREG_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
# GLEIF lists Norwegian legal entities under both Enhetsregisteret ids.
NORWAY_REGISTRIES = {"RA000472", "RA000473"}
ALLOWED_FORMS = {"ASA", "AS", "SE"}
MIN_SHARES = 100_000
MAX_SHARES = 50_000_000_000


def orgnr_from_gleif(payload: dict) -> tuple[Optional[dict], str]:
    """Pick the single usable GLEIF record carrying a Norwegian registry id."""
    rows = [r for r in (payload or {}).get("data") or [] if isinstance(r, dict)]
    usable = []
    for row in rows:
        attrs = row.get("attributes") or {}
        entity = attrs.get("entity") or {}
        if str(entity.get("status") or "").upper() == "INACTIVE":
            continue
        if str((attrs.get("registration") or {}).get("status") or "").upper() in {"RETIRED", "ANNULLED", "DUPLICATE"}:
            continue
        usable.append((row, entity))
    if not usable:
        return None, "gleif_no_active_record"
    if len(usable) > 1:
        return None, f"gleif_ambiguous_{len(usable)}"
    row, entity = usable[0]
    registered_at = ((entity.get("registeredAt") or {}).get("id") or "").upper()
    if registered_at not in NORWAY_REGISTRIES:
        return None, f"not_norwegian_register:{registered_at or 'none'}"
    orgnr = re.sub(r"\D", "", str(entity.get("registeredAs") or ""))
    if len(orgnr) != 9:
        return None, "gleif_no_orgnr"
    return {"lei": str(row.get("id") or "").upper(), "orgnr": orgnr,
            "legal_name": ((entity.get("legalName") or {}).get("name") or "")}, "ok"


def _fold(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").casefold())


def share_capital_from_brreg(payload: dict, orgnr: str, legal_name: str = "") -> tuple[Optional[dict], str]:
    if not isinstance(payload, dict) or str(payload.get("organisasjonsnummer") or "") != orgnr:
        return None, "brreg_identity_mismatch"
    if legal_name and _fold(legal_name) != _fold(payload.get("navn")):
        return None, "brreg_name_mismatch"
    if payload.get("konkurs") or payload.get("underAvvikling") or payload.get("underTvangsavviklingEllerTvangsopplosning"):
        return None, "brreg_not_active"
    form = str(((payload.get("organisasjonsform") or {}).get("kode")) or "").upper()
    if form not in ALLOWED_FORMS:
        return None, f"brreg_form_{form or 'none'}"
    capital = payload.get("kapital") or {}
    if not capital:
        return None, "brreg_no_capital"
    if str(capital.get("type") or "") != "Aksjekapital":
        return None, f"brreg_capital_type_{capital.get('type')}"
    if str(capital.get("valuta") or "").upper() != "NOK":
        return None, f"brreg_capital_currency_{capital.get('valuta')}"
    shares = capital.get("antallAksjer")
    if not isinstance(shares, int) or isinstance(shares, bool) or not MIN_SHARES <= shares <= MAX_SHARES:
        return None, f"brreg_implausible_count_{shares}"
    return {"shares": float(shares), "as_of": capital.get("innfortDato"),
            "capital_nok": capital.get("belop"), "legal_name": payload.get("navn")}, "ok"
