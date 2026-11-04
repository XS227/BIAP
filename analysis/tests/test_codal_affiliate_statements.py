import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import liara_codal_fetcher as lf
from codal_data import CodalFiling
from financial_scope import is_affiliate_statement, select_scope_filings

OWN = "صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی شده)"
AFF = "صورت‌های مالی  سال مالی منتهی به ۱۴۰۴/۰۹/۳۰ (حسابرسی شده) (شرکت راهبر ترابر انرژی)"


def filing(title, no="1"):
    return CodalFiling(no, title, None, None, None, None, None, "https://excel.codal.ir/x", None)


def test_affiliate_title_is_detected_in_fetcher_and_scope():
    assert lf.is_affiliate_statement(AFF) and is_affiliate_statement(AFF)
    assert not lf.is_affiliate_statement(OWN) and not is_affiliate_statement(OWN)
    assert not is_affiliate_statement(None)


def test_scope_selection_prefers_own_statements_over_newer_affiliate_ones():
    scope, chosen = select_scope_filings([filing(AFF, "9"), filing(OWN, "1")])
    assert scope == "consolidated" and [f.tracing_no for f in chosen] == ["1"]


def test_scope_selection_returns_nothing_when_only_affiliate_statements_exist():
    assert select_scope_filings([filing(AFF, "9")]) == (None, [])
