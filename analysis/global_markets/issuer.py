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
_LEGAL = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|plc|ltd|limited|ag|se|sa|nv|ab|asa|spa|holdings?)\b")


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def normalized_issuer_name(name: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").lower())
    text = _CLASS_SUFFIX.sub(" ", text)
    text = _LEGAL.sub(" ", text)
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
    name = normalized_issuer_name(_get(obj, "name") or _get(obj, "issuerName") or "")
    country = str(_get(obj, "country") or "").upper()
    if name:
        return f"NAME:{country}:{name}"
    # Unknown issuer: fall back to the security so nothing is merged by guess.
    return f"SECURITY:{country}:{str(_get(obj, 'exchange') or '').upper()}:{str(_get(obj, 'ticker') or '').upper()}"


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
    for row in rows:
        key = issuer_key_of(_row_identity(row))
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
