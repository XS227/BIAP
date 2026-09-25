from __future__ import annotations

import pytest

from global_markets.nzx_issuer import parse_nzx_limited_annual_report


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
