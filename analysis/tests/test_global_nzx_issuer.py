from __future__ import annotations

import pytest

from global_markets.nzx_issuer import (
    parse_nzx_limited_annual_report,
    parse_scales_annual_report,
    parse_summerset_annual_report,
)


def test_parse_nzx_limited_primary_statements():
    text = """
Group Income Statement
For the year ended 31 December 2025
Note
2025
$000
2024
Restated
$000
Operating revenue 8/9 128,948 120,122
Operating earnings (EBITDA) 2/8 51,689 46,549
Profit for the year 8 21,475 25,033
Basic (cents per share) 8/14.1 6.5 7.7

Group Statement of Financial Position
As at 31 December 2025
2025
$000
2024
$000
Cash and cash equivalents 15 32,055 28,825
Total assets 277,389 282,434
Total liabilities 155,204 162,749
Total equity attributable to shareholders 122,185 119,685

Group Statement of Cash Flows
For the year ended 31 December 2025
2025
$000
2024
$000
Net cash provided by operating activities 15.2 39,492 35,887
"""
    metrics=parse_nzx_limited_annual_report(text)
    assert metrics["revenue"] == pytest.approx(128_948_000)
    assert metrics["net_income"] == pytest.approx(21_475_000)
    assert metrics["cash_and_equivalents"] == pytest.approx(32_055_000)
    assert metrics["total_assets"] == pytest.approx(277_389_000)
    assert metrics["total_liabilities"] == pytest.approx(155_204_000)
    assert metrics["total_equity"] == pytest.approx(122_185_000)
    assert metrics["operating_cash_flow"] == pytest.approx(39_492_000)
    assert metrics["eps"] == pytest.approx(0.065)



def test_parse_summerset_primary_statements():
    text = """
Consolidated Income Statement
For the year ended 31 December 2025
2025 2024
Restated
NOTE $000 $000
Care fees and village services 4 223,616 197,165
Deferred management fees 4 137,245 121,446
Other income 4 913 1,292
Total revenue 361,774 319,903
Operating profit before finance costs 273,156 374,235
Profit for the period 259,720 331,958
Basic earnings per share (cents) 18 108.12 141.30

Consolidated Statement of Financial Position
As at 31 December 2025
2025 2024
Restated
NOTE $000 $000
Cash and cash equivalents 6,046 11,705
Total assets 9,234,870 8,041,075
Total liabilities 5,907,008 5,096,539
Total equity attributable to shareholders 3,327,862 2,944,536

Consolidated Statement of Cash Flows
For the year ended 31 December 2025
2025 2024
Restated
$000 $000
Net cash flow from operating activities 548,176 443,172
"""
    metrics=parse_summerset_annual_report(text)
    assert metrics["revenue"] == pytest.approx(361_774_000)
    assert metrics["net_income"] == pytest.approx(259_720_000)
    assert metrics["cash_and_equivalents"] == pytest.approx(6_046_000)
    assert metrics["total_assets"] == pytest.approx(9_234_870_000)
    assert metrics["total_liabilities"] == pytest.approx(5_907_008_000)
    assert metrics["total_equity"] == pytest.approx(3_327_862_000)
    assert metrics["operating_cash_flow"] == pytest.approx(548_176_000)
    assert metrics["eps"] == pytest.approx(1.0812)


def test_parse_scales_primary_statements():
    text = """
Financial Statements
2025 2024
Note $000's $000's
Revenue B1 899,949 584,627
EBITDA 169,862 87,876
Profit before income tax expense 135,293 60,389
Profit for the year 117,698 49,648
Earnings per share attributable to equity holders of the company:
Basic earnings per share (cents) D5 70.7 21.3

CURRENT ASSETS
Cash and bank balances 64,672 53,753 77,638
TOT AL AS S E TS 899,853 615,580 586,499
TOTAL CURRENT LIABILITIES 196,700 95,963 62,590
TOTAL LIABILITIES 443,337 229,272 198,065
NET ASSETS 456,516 386,308 388,434
Consolidated Statement of Financial Position
as at 31 December 2025

Consolidated Statement of Cash Flows
for the year ended 31 December 2025
2025 2024
$000's $000's
Net cash provided by operating activities 95,765 97,557
Cash and cash equivalents at the end of the year 64,672 53,753
"""
    metrics=parse_scales_annual_report(text)
    assert metrics["revenue"] == pytest.approx(899_949_000)
    assert metrics["net_income"] == pytest.approx(117_698_000)
    assert metrics["cash_and_equivalents"] == pytest.approx(64_672_000)
    assert metrics["total_assets"] == pytest.approx(899_853_000)
    assert metrics["total_liabilities"] == pytest.approx(443_337_000)
    assert metrics["total_equity"] == pytest.approx(456_516_000)
    assert metrics["operating_cash_flow"] == pytest.approx(95_765_000)
    assert metrics["eps"] == pytest.approx(0.707)
