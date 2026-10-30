"""Name-based detector for funds / market-maker vehicles that have no standard company statements.

A match never deletes or hides data: the ingestion only uses it to stop nightly retries (a
"not applicable" marker in the worker state) after a company has failed with no verified data.
Anything uncertain goes to REVIEW_SYMBOLS and keeps retrying until a person decides.
"""
from __future__ import annotations

FUND = "fund"
REVIEW = "review"

NAME_MARKERS = ("اختصاصی بازارگردانی", "با درآمد ثابت")
NAME_PREFIXES = ("مشترک",)
SYMBOL_SUFFIXES = (" ثابت", " بازار", " سهام")
FUND_SYMBOLS = frozenset({"تمشک", "رابین"})  # funds whose symbol/name carry no generic marker
REVIEW_SYMBOLS = frozenset({"صایند", "کامیاب"})
REVIEW_NAME_MARKERS = ("آشنا",)
# Real companies (operating or holding) that must keep retrying whatever their name looks like.
NEVER_NOT_APPLICABLE = frozenset({"سخرم", "ستبرا", "ستوسعه شیمیائی"})


def _norm(text: object) -> str:
    return " ".join(str(text or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").split())


def classify(symbol: object, name: object) -> str | None:
    """Return FUND, REVIEW or None (ordinary company: keep retrying)."""
    sym, nm = _norm(symbol), _norm(name)
    if sym in {_norm(s) for s in NEVER_NOT_APPLICABLE}:
        return None
    if sym in {_norm(s) for s in REVIEW_SYMBOLS} or any(_norm(m) in nm for m in REVIEW_NAME_MARKERS):
        return REVIEW
    if sym in {_norm(s) for s in FUND_SYMBOLS}:
        return FUND
    if any(sym.endswith(_norm(s)) for s in SYMBOL_SUFFIXES):
        return FUND
    if any(_norm(m) in nm for m in NAME_MARKERS) or any(nm.startswith(_norm(p)) for p in NAME_PREFIXES):
        return FUND
    return None
