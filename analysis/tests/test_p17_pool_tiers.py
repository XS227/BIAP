"""P1.7 (v2): BUY = top 10 % of the Evidence-PASS, confidence >= 0.45 pool, score >= 0.10; ACCUMULATE = top 25 %, score >= 0.05."""
import pytest

from global_markets import investment_mode as im

CFG = im.InvestmentConfig()


@pytest.fixture(autouse=True)
def _v2(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")


def test_pool_position_decides_and_floors_apply():
    t = im._tier_v2
    assert t(0, 100, 0, 20, 0.30, CFG, 6) == "BUY"
    assert t(0, 100, 0, 20, 0.09, CFG, 6) == "ACCUMULATE"        # below the 0.10 BUY floor, above 0.05
    assert t(0, 100, 0, 20, 0.04, CFG, 6) == "HOLD"              # below both floors


def test_fractions_and_outside_pool():
    t = im._tier_v2
    assert t(9, 100, 2, 20, 0.30, CFG, 6) == "ACCUMULATE"        # 3/20 = 15 %
    assert t(9, 100, 4, 20, 0.30, CFG, 6) == "ACCUMULATE"        # 5/20 = 25 %
    assert t(9, 100, 5, 20, 0.30, CFG, 6) == "HOLD"
    assert t(0, 100, None, 20, 0.50, CFG, 6) == "HOLD"           # outside the pool never earns BUY / ACCUMULATE
    assert t(0, 100, 0, 20, 0.30, CFG, 3) == "ACCUMULATE"        # BUY needs 4 agents with data


def test_negative_side_is_unchanged():
    assert im._tier_v2(99, 100, None, 0, -0.5, CFG, 6) == im._tier(99, 100, -0.5, CFG, 6) == "SELL"
