from __future__ import annotations

import pytest

from global_markets.swiss_issuer import parse_nestle_annual_financials


def test_parse_nestle_primary_annual_statements():
    text = """
Consolidated income statement
for the year ended December 31, 2025
In millions of CHF
Notes 2025 2024
Sales 3 89 490 91 354
Operating profit 12 277 14 724
Profit for the year 9 254 11 174
of which attributable to shareholders of the parent (Net profit) 9 033 10 884
Basic earnings per share 15 3.51 4.19

Consolidated balance sheet
as at December 31, 2025
In millions of CHF
Notes 2025 2024
Cash and cash equivalents 12/16 4 579 5 556
Total current assets 31 969 35 188
Total assets 127 151 139 264
Financial debt 12 11 606 11 863
Total current liabilities 40 694 42 863
Financial debt 12 46 246 51 697
Total liabilities 94 093 102 571
Total equity 33 058 36 693

Consolidated cash flow statement
for the year ended December 31, 2025
In millions of CHF
Notes 2025 2024
Cash generated from operations 16 861 19 593
Operating cash flow 15 904 16 675
Capital expenditure 8 (4 527) (5 638)
"""
    m=parse_nestle_annual_financials(text)
    assert m["revenue"] == pytest.approx(89_490_000_000)
    assert m["revenue_prev"] == pytest.approx(91_354_000_000)
    assert m["revenue_yoy_pct"] == pytest.approx(-2.0404142128)
    assert m["net_income"] == pytest.approx(9_033_000_000)
    assert m["net_margin_pct"] == pytest.approx(10.0938652363)
    assert m["eps"] == pytest.approx(3.51)
    assert m["current_assets"] == pytest.approx(31_969_000_000)
    assert m["total_assets"] == pytest.approx(127_151_000_000)
    assert m["current_assets"] < m["total_assets"]
    assert m["current_liabilities"] == pytest.approx(40_694_000_000)
    assert m["total_liabilities"] == pytest.approx(94_093_000_000)
    assert m["total_equity"] == pytest.approx(33_058_000_000)
    assert m["cash_and_equivalents"] == pytest.approx(4_579_000_000)
    assert m["operating_cash_flow"] == pytest.approx(15_904_000_000)
    assert m["free_cash_flow"] == pytest.approx(11_377_000_000)
    assert m["total_debt"] == pytest.approx(57_852_000_000)
