import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs" / "validation" / "tools"))
import de_option_ab_eval as ev  # noqa: E402

F = json.load(open(ROOT / "docs" / "validation" / "DE_PEER_EVIDENCE_E6_2026-10-17.json"))["issuers"]
PZS = {"revenue": 10000.0, "net_income": 4850000.0, "eps": 0.18, "pe": 14.33}
Z29 = {"revenue": 0.0, "net_income": -2330000.0, "eps": -0.47}
RKB = {"revenue": 0.0, "net_income": 290000.0, "eps": 0.34}
BFV = {"revenue": None, "net_income": 27340000.0, "eps": 2.09}
DBAN = {"revenue": None, "net_income": 26400000.0, "eps": 1.4, "pe": 13.43}
VNA = {"revenue": 5061300000.0, "net_income": 3723000000.0, "eps": 4.39}


def f(isin):
    return F[isin]


def test_baseline_rule_does_not_admit_any_of_the_six():
    for co, isin in ((PZS, "DE0006942808"), (Z29, "DE000A2LQ2D0"), (RKB, "DE0008103102"), (BFV, "DE0005221303"), (DBAN, "DE000A1TNUT7"), (VNA, "DE000A1ML7J1")):
        assert not ev.strict(co, f(isin))


def test_rule_a_only_scherzer():
    assert ev.rule_a(PZS, f("DE0006942808"))
    assert not any(ev.rule_a(c, f(i)) for c, i in ((VNA, "DE000A1ML7J1"), (BFV, "DE0005221303"), (DBAN, "DE000A1TNUT7"), (Z29, "DE000A2LQ2D0")))


def test_rule_b_requires_zero_revenue_and_no_revenue_line():
    assert ev.rule_b(Z29, f("DE000A2LQ2D0")) and ev.rule_b(RKB, f("DE0008103102"))
    assert not ev.rule_b(BFV, f("DE0005221303"))                                  # revenue None, not 0.0
    assert not ev.rule_b({**PZS, "revenue": 0.0}, f("DE0006942808"))             # filing prints a revenue line -> 0.0 would be a data error, not a shell
    assert not ev.rule_b({**Z29, "net_income": -1_000_000.0}, f("DE000A2LQ2D0"))  # NI must match


def test_rule_b2_derives_eps_to_the_cent():
    assert ev.rule_b2(RKB, f("DE0008103102"))
    assert not ev.rule_b2(Z29, f("DE000A2LQ2D0"))                     # loss-making shell: evidence valid, not an eligible peer
    assert ev.rule_b(Z29, f("DE000A2LQ2D0"))                          # rule B (sensitivity only) would still admit it
    assert not ev.rule_b2({**RKB, "eps": 0.50}, f("DE0008103102"))


def test_corrections_only_unambiguous_printed_values():
    assert ev.corrections(PZS, f("DE0006942808")) == {"revenue": 10594.89}
    assert ev.corrections(DBAN, f("DE000A1TNUT7")) == {"net_income": 24698000, "eps": 1.39}
    assert ev.corrections(VNA, f("DE000A1ML7J1")) == {}                           # revenue definition ambiguous, stored NI already matches
    assert ev.corrections(BFV, f("DE0005221303")) == {}                           # printed EpS uses a different numerator


def test_correction_rescales_pe_at_constant_price():
    co = ev.apply_correction(dict(DBAN), {"net_income": 24698000, "eps": 1.39})
    assert abs(co["pe"] * 1.39 - 13.43 * 1.4) < 1e-9
    assert ev.strict(co, f("DE000A1TNUT7"))


def test_tolerance_is_not_evidence_for_small_figures():
    assert not ev.near(10000.0, 10594.89)
    assert ev.near(290000.0, 292000.0) and ev.near(-2330000.0, -2334332.05)
