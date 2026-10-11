from global_markets.distress import distress_agent
from global_markets.models import GlobalCompany


def _co(**kw):
    base = dict(country="GB", exchange="LSE", ticker="X", name="X", currency="GBP")
    base.update(kw)
    return GlobalCompany(**base)


def test_unclassified_bank_balance_sheet_not_scored_as_corporate():
    bank = _co(total_assets=3233e9, total_equity=205e9, operating_income=30e9, interest_expense=60e9)
    result = distress_agent(bank)
    assert result.status == "NOT_APPLICABLE"
    assert not result.positive_block


def test_unclassified_industrial_still_scored():
    corp = _co(total_assets=137e9, total_equity=52e9, operating_income=5e9, interest_expense=0.8e9)
    assert distress_agent(corp).status != "NOT_APPLICABLE"
