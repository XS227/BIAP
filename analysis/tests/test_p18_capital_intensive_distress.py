from global_markets.distress import distress_agent, is_capital_intensive
from global_markets.models import GlobalCompany


def co(**kw):
    base = dict(country="NO", exchange="OSL", currency="NOK", ticker="AKRBP", name="Aker BP", sector="Energy",
                industry="Oil, Gas and Coal", current_assets=1000.0, current_liabilities=2200.0,
                retained_earnings=-500.0, operating_income=900.0, total_assets=10000.0, total_equity=3500.0,
                total_liabilities=6500.0, net_income=600.0, interest_expense=200.0)
    base.update(kw)
    return GlobalCompany(**base)


def test_altman_alone_does_not_block_energy_in_v2():
    d = distress_agent(co(), capital_intensive_guard=True)
    assert d.altman_zone == "DISTRESS"
    assert d.positive_block is False and d.status == "ELEVATED_RISK"
    assert "does not govern" in d.reasoning and "zmijewski" in d.reasoning


def test_v1_unchanged():
    d = distress_agent(co(), capital_intensive_guard=False)
    assert d.positive_block is True and d.status == "HIGH_RISK"


def test_default_follows_env(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    assert distress_agent(co()).positive_block is True
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert distress_agent(co()).positive_block is False


def test_other_models_still_block():
    assert distress_agent(co(interest_expense=2000.0), capital_intensive_guard=True).positive_block is True
    assert distress_agent(co(total_equity=-1.0), capital_intensive_guard=True).positive_block is True
    assert distress_agent(co(net_income=-3000.0), capital_intensive_guard=True).positive_block is True


def test_non_capital_intensive_still_blocks():
    c = co(sector="Technology", industry="Software")
    assert not is_capital_intensive(c)
    assert distress_agent(c, capital_intensive_guard=True).positive_block is True
