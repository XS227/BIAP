from datetime import date

from global_markets.esef import ESEFFundamentalsProvider

P = "2025-01-01T00:00:00/2026-01-01T00:00:00"


def _fact(concept, value):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": P, "unit": "iso4217:EUR"}}


def _interest(*facts):
    out = ESEFFundamentalsProvider().normalized_fields(list(facts), date(2025, 12, 31))
    return out["interest_expense"]


def test_gross_finance_costs_offset_by_finance_income_use_reported_net_cost():
    # Eni FY2025: FinanceCosts 8.17bn vs FinanceIncome 7.2bn, FinanceIncomeCost -0.819bn
    assert _interest(
        _fact("ifrs-full:FinanceCosts", 8_170e6),
        _fact("ifrs-full:FinanceIncome", 7_196e6),
        _fact("ifrs-full:FinanceIncomeCost", -819e6),
    ) == 819e6


def test_gross_up_without_reported_net_keeps_gross_never_invents_net():
    assert _interest(_fact("ifrs-full:FinanceCosts", 8_170e6), _fact("ifrs-full:FinanceIncome", 7_196e6)) == 8_170e6


def test_net_finance_income_after_gross_up_is_withheld():
    assert _interest(
        _fact("ifrs-full:FinanceCosts", 1_000e6),
        _fact("ifrs-full:FinanceIncome", 950e6),
        _fact("ifrs-full:FinanceIncomeCost", 50e6),
    ) is None


def test_ordinary_cash_rich_issuer_keeps_gross_costs():
    assert _interest(
        _fact("ifrs-full:FinanceCosts", 100e6),
        _fact("ifrs-full:FinanceIncome", 85e6),
        _fact("ifrs-full:FinanceIncomeCost", -15e6),
    ) == 100e6


def test_plain_finance_costs_kept_when_income_is_small():
    assert _interest(_fact("ifrs-full:FinanceCosts", 100e6), _fact("ifrs-full:FinanceIncome", 5e6)) == 100e6


def test_tagged_interest_expense_always_wins():
    assert _interest(
        _fact("ifrs-full:InterestExpense", 300e6),
        _fact("ifrs-full:FinanceCosts", 8_170e6),
        _fact("ifrs-full:FinanceIncome", 7_196e6),
    ) == 300e6
