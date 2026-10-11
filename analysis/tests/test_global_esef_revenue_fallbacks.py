"""ESEF top-line fallbacks when no IFRS Revenue total is tagged.

- RevenueAndOperatingIncome ("sum driftsinntekter", e.g. Komplett ASA) with
  separately tagged other income netted out (signed);
- RevenueFromSaleOfGoods as the only revenue line (Sildarvinnslan FY2024),
  never when services revenue is also tagged;
- continuing-operations EPS only when no discontinued result is tagged.
"""
from datetime import date

from global_markets.esef import ESEFFundamentalsProvider

END = date(2025, 12, 31)
FY25 = "2025-01-01/2025-12-31"
FY24 = "2024-01-01/2024-12-31"


def fact(concept, value, period, unit="iso4217:NOK"):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit}}


def _norm(facts):
    return ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider).normalized_fields(facts, END)


def _base():
    return [fact("ifrs-full:ProfitLoss", 50e6, FY25), fact("ifrs-full:ProfitLoss", 40e6, FY24), fact("ifrs-full:Assets", 900e6, "2025-12-31")]


def test_revenue_and_operating_income_nets_other_income():
    r = _norm(_base() + [
        fact("ifrs-full:RevenueAndOperatingIncome", 1_020e6, FY25), fact("ifrs-full:OtherIncome", 20e6, FY25),
        fact("ifrs-full:RevenueAndOperatingIncome", 910e6, FY24), fact("ifrs-full:OtherIncome", 10e6, FY24),
    ])
    assert r["revenue"] == 1_000e6
    assert r["revenue_prev"] == 900e6
    assert r["__normalization_meta__"]["revenue_method"] == "revenue_and_operating_income_minus_other_income"


def test_mixed_netting_years_give_no_growth_comparison():
    r = _norm(_base() + [
        fact("ifrs-full:RevenueAndOperatingIncome", 1_020e6, FY25), fact("ifrs-full:OtherIncome", 20e6, FY25),
        fact("ifrs-full:RevenueAndOperatingIncome", 910e6, FY24),
    ])
    assert r["revenue"] == 1_000e6
    assert r["revenue_prev"] is None


def test_sale_of_goods_is_top_line_only_without_services_revenue():
    goods = [fact("ifrs-full:RevenueFromSaleOfGoods", 324.75e6, FY25), fact("ifrs-full:RevenueFromSaleOfGoods", 300e6, FY24)]
    assert _norm(_base() + goods)["revenue"] == 324.75e6
    with_services = _norm(_base() + goods + [fact("ifrs-full:RevenueFromRenderingOfServices", 80e6, FY25)])
    assert with_services["revenue"] is None


def test_ifrs_revenue_total_still_wins():
    r = _norm(_base() + [fact("ifrs-full:Revenue", 999e6, FY25), fact("ifrs-full:RevenueFromSaleOfGoods", 500e6, FY25),
                         fact("ifrs-full:RevenueAndOperatingIncome", 1_100e6, FY25)])
    assert r["revenue"] == 999e6


def test_continuing_eps_used_only_without_discontinued_result():
    eps = [fact("ifrs-full:BasicEarningsLossPerShareFromContinuingOperations", 1.25, FY25, unit="iso4217:NOK/xbrli:shares")]
    assert _norm(_base() + eps)["eps"] == 1.25
    disc = _norm(_base() + eps + [fact("ifrs-full:ProfitLossFromDiscontinuedOperations", -30e6, FY25)])
    assert disc["eps"] is None


def test_failed_fallback_keeps_previous_year_revenue():
    r = _norm(_base() + [fact("ifrs-full:Revenue", 206_890, FY24)])
    assert r["revenue"] is None
    assert r["revenue_prev"] == 206_890
