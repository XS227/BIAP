"""Shell plc (SHEL): statement line 'Capital expenditure' is tagged with a generic IFRS concept; a reviewed LEI mapping unlocks FCF only for that issuer."""
from datetime import date

from global_markets.esef import ESEFFundamentalsProvider

SHELL_LEI = "21380068P1DRHMJ8KU70"


def _fact(concept, value, lei, period="2025-01-01/2025-12-31"):
    return {"dimensions": {"concept": concept, "entity": f"scheme:{lei}", "period": period, "unit": "iso4217:USD"}, "value": str(value), "decimals": "-6"}


def _facts(lei):
    return [
        _fact("ifrs-full:CashFlowsFromUsedInOperatingActivities", 42_863_000_000, lei),
        _fact("ifrs-full:PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities", 18_947_000_000, lei),
        # segment cash-capex extension fact must never be used
        _fact("shel:CashOutflowForTotalCashCapitalExpenditure", 20_915_000_000, lei),
    ]


def _normalize(lei):
    return ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider).normalized_fields(_facts(lei), date(2025, 12, 31))


def test_reviewed_issuer_gets_fcf_from_statement_capex_line():
    out = _normalize(SHELL_LEI)
    assert out["operating_cash_flow"] == 42_863_000_000
    assert out["free_cash_flow"] == 42_863_000_000 - 18_947_000_000
    assert out["__normalization_meta__"]["capex_method"].startswith("reviewed_statement_line:")


def test_other_issuers_do_not_inherit_the_mapping():
    out = _normalize("529900T8BM49AURSDO55")
    assert out["free_cash_flow"] is None
    assert out["__normalization_meta__"]["capex_method"] is None
