"""Research-paper scripts: regression comparison, gate attribution order, market scope."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import regression_check as RC  # noqa: E402
import research_common as C  # noqa: E402
from global_markets import investment_mode as im  # noqa: E402


def _market(cons_buy, inv_buy):
    return {"conservative": {"BUY": cons_buy, "HOLD": 100}, "investment": {"BUY": inv_buy, "SELL": 40}}


def test_regression_flags_only_changes_above_five_percent():
    base = {"US:NYSE": _market(20, 100)}
    assert RC.compare(base, {"US:NYSE": _market(20, 105)}) == []                    # exactly 5% is allowed
    warn = RC.compare(base, {"US:NYSE": _market(20, 106)})
    assert len(warn) == 1 and "investment BUY: 100 -> 106" in warn[0]
    assert any("conservative BUY" in w for w in RC.compare(base, {"US:NYSE": _market(18, 100)}))


def test_regression_zero_baseline_and_missing_market():
    base = {"NL": {"conservative": {"SELL": 0}, "investment": {"SELL": 8}}}
    assert RC.compare(base, {"NL": {"conservative": {"SELL": 1}, "investment": {"SELL": 8}}})
    assert any("missing" in w for w in RC.compare(base, {}))


def test_gate_group_uses_cascade_order_not_engine_order():
    assert C.gate_group(["CONFIDENCE_BELOW_0.35", "SCORE_BELOW_0.25"]) == "score"
    assert C.gate_group(["PEER_GROUP_BELOW_8", "DISTRESS_NOT_LOW_RISK"]) == "distress"
    assert C.gate_group(["NO_INDEPENDENT_POSITIVE_SIGNAL"]) == "independent_signal"
    assert C.gate_group([]) == "PASS"


def test_scope_lists_the_ten_countries_and_germany_is_one_market():
    assert {m.split(":")[0] for m in im.INVESTMENT_MODE_MARKETS} == {"US", "GB", "IT", "SE", "NO", "DE", "FR", "NL", "FI", "ES"}
    assert im.in_scope("DE:FRANKFURT", True) and not im.in_scope("CA:TSX", True) and im.in_scope("CA:TSX", False)
    assert C.market_of("DE:XETRA") == C.market_of("DE:FRANKFURT") == "DE"
