"""Volvo Car AB FY2025 regression on facts from the official FI ESEF package.

Fixture: inline-XBRL facts of Finansinspektionen document
FI-FINANSCENTRALEN:61816 (5299000EAMGGBEYP7J33-2025-12-31-1-en.xhtml, LEI
5299000EAMGGBEYP7J33 = Volvo Car AB, org. 556810-8988), filtered to the
concepts the normalizer reads plus three lines it must not use.
"""
import json
from datetime import date
from pathlib import Path

from global_markets.esef import ESEFFundamentalsProvider

FIXTURE = Path(__file__).parent / "fixtures" / "volvo_car_fy2025_esef_facts.json"


def _normalized(facts=None):
    facts = facts if facts is not None else json.loads(FIXTURE.read_text(encoding="utf-8"))
    return ESEFFundamentalsProvider().normalized_fields(facts, date(2025, 12, 31))


def test_volvo_car_fy2025_statements():
    result = _normalized()
    assert result["reporting_currency"] == "SEK"
    assert result["revenue"] == 357_263_000_000
    assert result["revenue_prev"] == 400_234_000_000
    assert result["operating_income"] == 303_000_000
    assert result["net_income"] == -2_968_000_000
    assert result["total_assets"] == 373_172_000_000
    assert result["total_equity"] == 148_378_000_000
    # No ifrs-full:Liabilities tag: assets - equity of the same balance sheet.
    assert result["total_liabilities"] == 373_172_000_000 - 148_378_000_000
    assert result["current_liabilities"] == 151_254_000_000


def test_volvo_car_fy2025_credit_inputs_are_source_backed():
    result = _normalized()
    meta = result.pop("__normalization_meta__")
    # Closing balance of the retained-earnings column (FY2024 closing 95,045).
    assert result["retained_earnings"] == 101_347_000_000
    assert meta["retained_earnings_method"] == "equity_statement_retained_earnings_column"
    # No EBITDA tag: operating income 303 + cash-flow D&A add-back 23,945 (MSEK).
    assert meta["depreciation_amortisation"] == 23_945_000_000
    assert meta["depreciation_amortisation_method"] == "cash_flow_da_add_back"
    assert result["ebitda"] == 303_000_000 + 23_945_000_000
    # No borrowings line: bonds (current 1,500 + non-current 21,645) plus IFRS
    # loans received (current 922 + non-current 6,723). Issuer VOL:Other*
    # LiabilitiesInterestBearing lines are not standard debt and are ignored.
    assert result["total_debt"] == 1_500_000_000 + 21_645_000_000 + 922_000_000 + 6_723_000_000
    assert meta["debt_method"] == (
        "sum_of_bonds_and_loans:current_bonds,current_other_loans,noncurrent_bonds,noncurrent_other_loans"
    )
    # CAPEX is PP&E only (22,825); intangible purchases (17,252) are not added.
    assert meta["capex"] == 22_825_000_000
    assert result["free_cash_flow"] == 34_625_000_000 - 22_825_000_000
    # FFO = EBITDA 24,248 - interest paid 1,538 + received 1,929 - taxes paid 3,724.
    assert meta["ffo"] == 20_915_000_000


def test_volvo_car_bonds_without_loans_lines_stay_bonds_only():
    facts = [
        f for f in json.loads(FIXTURE.read_text(encoding="utf-8"))
        if "LoansReceived" not in f["dimensions"]["concept"]
    ]
    result = _normalized(facts)
    assert result["total_debt"] == 1_500_000_000 + 21_645_000_000
    assert result["__normalization_meta__"]["debt_method"] == "sum_of_bonds_and_loans:current_bonds,noncurrent_bonds"
