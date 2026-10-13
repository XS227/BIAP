"""Issuer identity for BIAP Global rankings and portfolio concentration.

A security (ticker/ISIN) is not an issuer: GOOG and GOOGL are two securities
of one legal entity, with one balance sheet and one risk. Rankings of
*companies* and concentration limits must therefore work on the issuer, while
the separate securities stay visible and tradeable.
"""
from __future__ import annotations

import re
from typing import Any

_CLASS_SUFFIX = re.compile(
    r"\b(class|series)\s+[a-z0-9]\b|\b(common|ordinary|preferred|preference|voting|non[- ]voting|"
    r"restricted|capital|depositary|ads|adr|shares?|stock|units?|ord|cl)\b|\b[a-z]\s+shares?\b",
)
# German share-class markers in Deutsche Boerse instrument names: Stamm (ST), Vorzug (VZ/VZO),
# Namens (NA), Inhaber (INH), "ohne Nennwert" (O.N. -> "on"). Removed only from the issuer-name key;
# issuers still merge only when the remaining legal name is identical within the same country.
_DE_CLASS_SUFFIX = re.compile(r"\b(na|on|inh|st|vz|vzo|vorzugsaktien|stammaktien|namensaktien|inhaberaktien)\b")
# Depositary/registry/foreign-listing markers: the security is a listing of a
# foreign issuer, so its name key must not be pinned to the listing country.
_DEPOSITARY = re.compile(
    r"\b(new york registry|ny registry|registry shares?|american depositary|depositary (shares?|receipts?)|"
    r"adrs?|ads|sponsored|unsponsored)\b"
)
_LEGAL = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|plc|ltd|limited|ag|se|sa|nv|ab|asa|spa|holdings?)\b")


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _clean(name: str) -> str:
    text = str(name or "").lower().replace("&", " and ")
    # Collapse dotted legal suffixes first: "N.V." / "S.p.A." / "plc." -> nv / spa.
    text = re.sub(r"\b([a-z])\.(?=[a-z]\b)", r"\1", text)
    text = re.sub(r"\b([a-z])\.(?=\s|$)", r"\1", text)
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def is_depositary_name(name: str) -> bool:
    return bool(_DEPOSITARY.search(_clean(name)))


def normalized_issuer_name(name: str, country: str = "") -> str:
    text = _DEPOSITARY.sub(" ", _clean(name))
    text = _CLASS_SUFFIX.sub(" ", text)
    if country == "DE":
        text = _DE_CLASS_SUFFIX.sub(" ", text)
    text = _LEGAL.sub(" ", text)
    text = re.sub(r"\bnew york\b", " ", text) if text.strip().endswith("new york") else text
    return " ".join(text.split())


def issuer_key_of(obj: Any) -> str:
    """Stable issuer key: LEI > SEC CIK > country + normalized legal name."""
    lei = str(_get(obj, "lei") or "").strip().upper()
    if len(lei) == 20:
        return f"LEI:{lei}"
    raw = _get(obj, "raw_provider_fields") or _get(obj, "rawProviderFields") or {}
    cik = raw.get("sec_cik") if isinstance(raw, dict) else None
    if cik not in (None, ""):
        try:
            return f"CIK:{int(cik)}"
        except (TypeError, ValueError):
            pass
    raw_name = _get(obj, "name") or _get(obj, "issuerName") or ""
    country = str(_get(obj, "country") or "").upper()
    name = normalized_issuer_name(raw_name, country)
    if name:
        if is_depositary_name(raw_name):
            return f"NAME:*:{name}"  # foreign issuer listed locally; matched to its home listing
        return f"NAME:{country}:{name}"
    # Unknown issuer: fall back to the security so nothing is merged by guess.
    return f"SECURITY:{country}:{str(_get(obj, 'exchange') or '').upper()}:{str(_get(obj, 'ticker') or '').upper()}"


# Independently verified cross-listing bridges (SEC CIK -> legal-entity LEI).
# ASML: SEC CIK 937966 (20-F filer, NASDAQ NY registry shares); LEI 724500Y6DUVHQD6OXN27
# is the Euronext Amsterdam listing's FIRDS/GLEIF LEI.
VERIFIED_CIK_TO_LEI = {937966: "724500Y6DUVHQD6OXN27"}


def resolve_issuer_identities(identities: list[Any]) -> list[str]:
    """Issuer key per identity, merging cross-listings of one legal entity.

    1. ``VERIFIED_CIK_TO_LEI`` plus CIK<->LEI pairs asserted by a row that carries
       both identifiers map a SEC CIK to its LEI (conflicting assertions are ignored).
    2. A foreign-registrant listing (SEC CIK or depositary/registry name, i.e. a
       key that cannot match a home listing by itself) adopts the key of the
       other-country listing with the same normalized legal name, but only when
       that match is unique. Ambiguity keeps the keys apart; nothing is merged
       by guess and the other security stays visible in the response.
    """
    keys = [issuer_key_of(i) for i in identities]
    # A row that itself carries BOTH a 20-char LEI and a SEC CIK asserts the
    # CIK<->LEI link (e.g. BP p.l.c. on LSE). Learn it, but only when every
    # such row agrees on one LEI for that CIK; a conflict is never resolved by guess.
    learned: dict[int, set[str]] = {}
    for ident in identities:
        lei = str(_get(ident, "lei") or "").strip().upper()
        raw = _get(ident, "raw_provider_fields") or _get(ident, "rawProviderFields") or {}
        cik = raw.get("sec_cik") if isinstance(raw, dict) else None
        if len(lei) == 20 and cik not in (None, ""):
            try:
                learned.setdefault(int(cik), set()).add(lei)
            except (TypeError, ValueError):
                pass
    cik_to_lei = {cik: next(iter(leis)) for cik, leis in learned.items() if len(leis) == 1}
    cik_to_lei.update(VERIFIED_CIK_TO_LEI)
    for n, k in enumerate(keys):
        if k.startswith("CIK:") and int(k[4:]) in cik_to_lei:
            keys[n] = f"LEI:{cik_to_lei[int(k[4:])]}"
    countries = [str(_get(i, "country") or "").upper() for i in identities]
    names = [normalized_issuer_name(_get(i, "name") or _get(i, "issuerName") or "", c) for i, c in zip(identities, countries)]
    out = list(keys)
    for n, k in enumerate(keys):
        if not names[n] or not (k.startswith("CIK:") or k.startswith("NAME:*:")):
            continue
        homes = {
            keys[m] for m in range(len(keys))
            if m != n and names[m] == names[n] and countries[m] != countries[n]
            and not keys[m].startswith("CIK:") and not keys[m].startswith("NAME:*:")
        }
        if len(homes) == 1:
            out[n] = next(iter(homes))
    return out


def _row_identity(row: dict) -> dict:
    company = row.get("company") if isinstance(row.get("company"), dict) else {}
    return {
        "lei": company.get("lei") or row.get("lei"),
        "name": company.get("name") or row.get("name") or row.get("issuerName"),
        "country": company.get("country") or row.get("country"),
        "exchange": company.get("exchange") or row.get("exchange"),
        "ticker": company.get("ticker") or row.get("ticker"),
        "raw_provider_fields": company.get("raw_provider_fields") or company.get("rawProviderFields") or {},
    }


def collapse_issuers(rows: list[dict], rank) -> list[dict]:
    """One row per issuer for company rankings; other securities stay attached.

    ``rank(row)`` returns a sortable score. The best-ranked security leads; the
    rest are preserved under ``otherSecurities`` (never dropped) so share
    classes remain separately visible and independently tradeable.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    keys = resolve_issuer_identities([_row_identity(row) for row in rows])
    for row, key in zip(rows, keys):
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    out: list[dict] = []
    for key in order:
        members = sorted(groups[key], key=rank, reverse=True)
        lead = dict(members[0])
        lead["issuerKey"] = key
        lead["otherSecurities"] = [
            {
                "country": ident["country"], "exchange": ident["exchange"], "ticker": ident["ticker"],
                "score": m.get("score"), "confidence": m.get("confidence"),
            }
            for m in members[1:]
            for ident in (_row_identity(m),)
        ]
        out.append(lead)
    return out
