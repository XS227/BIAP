"""Rule-based classification of TSETMC/IFB instruments into explicit categories.

BIAP previously treated "in the CODAL issuer whitelist" as the only signal for
"is this a company". That conflated two different questions: (1) what kind of
instrument is this (share, fund, bond, option, rights issue, ...), and (2)
should this instrument's *company* be collected. This module answers (1) only,
deterministically and without any network access, from fields already present
on a TSETMC market-watch row (symbol, name, market, yVal/paper_type). CODAL
stays a downstream enrichment/verification source (see company_builder.py) and
is intentionally not consulted here.

Classification is conservative: a genuine company category is only returned
when a positive signal is found. Everything else falls back to "unknown"
rather than being silently guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass

# Canonical category vocabulary. Keep in sync with the docs/task spec.
CATEGORY_OPERATING_COMPANY = "operating_company"
CATEGORY_BANK = "bank"
CATEGORY_INSURANCE_COMPANY = "insurance_company"
CATEGORY_INVESTMENT_COMPANY = "investment_company"
CATEGORY_HOLDING_COMPANY = "holding_company"
CATEGORY_LISTED_FINANCIAL_COMPANY = "listed_financial_company"
CATEGORY_FUND_ETF = "fund_etf"
CATEGORY_BOND_DEBT = "bond_debt"
CATEGORY_OPTION_DERIVATIVE = "option_derivative"
CATEGORY_RIGHTS_ISSUE = "rights_issue"
CATEGORY_COMMODITY_INSTRUMENT = "commodity_instrument"
CATEGORY_DUPLICATE_SHARE_CLASS = "duplicate_share_class"
CATEGORY_UNKNOWN = "unknown"

ALL_CATEGORIES = (
    CATEGORY_OPERATING_COMPANY,
    CATEGORY_BANK,
    CATEGORY_INSURANCE_COMPANY,
    CATEGORY_INVESTMENT_COMPANY,
    CATEGORY_HOLDING_COMPANY,
    CATEGORY_LISTED_FINANCIAL_COMPANY,
    CATEGORY_FUND_ETF,
    CATEGORY_BOND_DEBT,
    CATEGORY_OPTION_DERIVATIVE,
    CATEGORY_RIGHTS_ISSUE,
    CATEGORY_COMMODITY_INSTRUMENT,
    CATEGORY_DUPLICATE_SHARE_CLASS,
    CATEGORY_UNKNOWN,
)

# Categories that represent a genuine, independently-investable issuer/company
# and therefore belong in the primary company research dataset.
COMPANY_CATEGORIES = frozenset({
    CATEGORY_OPERATING_COMPANY,
    CATEGORY_BANK,
    CATEGORY_INSURANCE_COMPANY,
    CATEGORY_INVESTMENT_COMPANY,
    CATEGORY_HOLDING_COMPANY,
    CATEGORY_LISTED_FINANCIAL_COMPANY,
})

# Categories that still map to a real company's issuer_id (so instrument ->
# company mapping is preserved) but that must never inflate the unique
# company count or consume a separate daily-enrichment slot.
COMPANY_LINKED_NON_PRIMARY_CATEGORIES = frozenset({
    CATEGORY_RIGHTS_ISSUE,
    CATEGORY_DUPLICATE_SHARE_CLASS,
})

# TSETMC yVal values for ordinary shares (verified against production
# GetMarketWatch payloads; see listed_company_ingestion.ORDINARY_SHARE_YVALS).
ORDINARY_SHARE_YVALS = frozenset({"300", "303", "307", "309", "313"})
# Verified TSETMC yVal for rights issues (حق تقدم); confirmed via production
# payload shape in listed_company_ingestion tests.
RIGHTS_ISSUE_YVAL = "400"

_ZWNJ_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "‌": " ", "‏": "", "‎": ""})


def normalize_text(value: object) -> str:
    """Normalize Persian text for keyword matching and key generation."""
    return " ".join(str(value or "").translate(_ZWNJ_MAP).split()).strip()


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


_RIGHTS_KEYWORDS = ("حق تقدم",)
_BOND_KEYWORDS = ("اوراق", "صکوک", "خزانه", "مرابحه", "اجاره", "منفعت")
_OPTION_KEYWORDS = ("اختیار خرید", "اختیار فروش", "اختیار معامله", "آتی")
_FUND_KEYWORDS = ("صندوق",)
_COMMODITY_KEYWORDS = ("سکه", "زعفران", "گواهی سپرده کالایی", "شمش")
_BANK_KEYWORDS = ("بانک",)
_INSURANCE_KEYWORDS = ("بیمه",)
_HOLDING_KEYWORDS = ("هلدینگ",)
_HOLDING_GROUP_KEYWORDS = ("گروه",)
_HOLDING_GROUP_QUALIFIERS = ("سرمایه", "توسعه")
_INVESTMENT_KEYWORDS = ("سرمایه گذاری",)
_LISTED_FINANCIAL_KEYWORDS = ("لیزینگ", "کارگزاری", "تامین سرمایه", "صرافی")


@dataclass(frozen=True)
class Classification:
    category: str
    reason: str

    def to_dict(self) -> dict:
        return {"category": self.category, "reason": self.reason}


def classify_instrument(
    *,
    symbol: str,
    name: str | None = None,
    market: str | None = None,
    paper_type: str | None = None,
) -> Classification:
    """Classify one TSETMC/IFB instrument row. Pure function, no I/O.

    ``symbol``/``name`` are matched on normalized Persian text; ``paper_type``
    is TSETMC's yVal. Order matters: more specific, less ambiguous categories
    (rights issues, bonds, options, funds, commodities) are checked before the
    broader financial-company buckets, which are checked before the
    ordinary-share fallback.
    """
    text = normalize_text(f"{symbol} {name or ''}")
    paper_type = str(paper_type or "").strip()

    if paper_type == RIGHTS_ISSUE_YVAL or _contains_any(text, _RIGHTS_KEYWORDS):
        return Classification(CATEGORY_RIGHTS_ISSUE, "rights-issue yVal or حق تقدم in name")

    if _contains_any(text, _BOND_KEYWORDS):
        return Classification(CATEGORY_BOND_DEBT, "bond/sukuk/treasury keyword in name")

    if _contains_any(text, _OPTION_KEYWORDS):
        return Classification(CATEGORY_OPTION_DERIVATIVE, "option/futures keyword in name")

    if _contains_any(text, _FUND_KEYWORDS):
        return Classification(CATEGORY_FUND_ETF, "صندوق (fund) keyword in name")

    if _contains_any(text, _COMMODITY_KEYWORDS):
        return Classification(CATEGORY_COMMODITY_INSTRUMENT, "commodity keyword in name")

    if _contains_any(text, _BANK_KEYWORDS):
        return Classification(CATEGORY_BANK, "بانک keyword in name")

    if _contains_any(text, _INSURANCE_KEYWORDS):
        return Classification(CATEGORY_INSURANCE_COMPANY, "بیمه keyword in name")

    if _contains_any(text, _HOLDING_KEYWORDS):
        return Classification(CATEGORY_HOLDING_COMPANY, "هلدینگ keyword in name")

    if _contains_any(text, _HOLDING_GROUP_KEYWORDS) and _contains_any(text, _HOLDING_GROUP_QUALIFIERS):
        return Classification(CATEGORY_HOLDING_COMPANY, "گروه + سرمایه/توسعه qualifier in name")

    if _contains_any(text, _INVESTMENT_KEYWORDS):
        return Classification(CATEGORY_INVESTMENT_COMPANY, "سرمایه گذاری keyword in name")

    if _contains_any(text, _LISTED_FINANCIAL_KEYWORDS):
        return Classification(CATEGORY_LISTED_FINANCIAL_COMPANY, "other financial-services keyword in name")

    if paper_type in ORDINARY_SHARE_YVALS or (market or "").upper() in {"TSE", "IFB", "IFB_BASE"}:
        return Classification(CATEGORY_OPERATING_COMPANY, "verified ordinary-share yVal or market flow")

    return Classification(CATEGORY_UNKNOWN, "no positive classification signal")


def base_issuer_symbol(symbol: str, name: str | None, category: str) -> str:
    """Return the symbol that should key the *underlying company* for dedup.

    For a rights issue, TSE convention appends the letter ``ح`` to the base
    ordinary-share ticker (e.g. ``فولادح`` for ``فولاد``); strip it so the
    rights instrument resolves to the same issuer as its ordinary share. Every
    other category keys on its own normalized symbol.
    """
    sym = normalize_text(symbol)
    if category == CATEGORY_RIGHTS_ISSUE:
        stripped = sym[:-1] if sym.endswith("ح") and len(sym) > 1 else sym
        if stripped:
            return stripped
        # Fall back to the name with the rights-issue phrase removed.
        base_name = normalize_text((name or "").replace("حق تقدم", ""))
        return base_name or sym
    return sym


def issuer_key(symbol: str, name: str | None, category: str) -> str | None:
    """Stable dedup key for the company this instrument belongs to.

    Returns ``None`` for categories that are not tied to a single genuine
    issuer (funds, bonds, options, commodities, unknown) — those instruments
    stay in the raw instrument registry but never get an issuer_id.
    """
    if category not in COMPANY_CATEGORIES and category not in COMPANY_LINKED_NON_PRIMARY_CATEGORIES:
        return None
    base = base_issuer_symbol(symbol, name, category)
    return base.upper() if base else None
