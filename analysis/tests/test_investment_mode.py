"""Investment decision mode (DECISION_MODE=investment): ranked BUY/ACCUMULATE/HOLD/REDUCE/SELL."""
import pytest

from global_markets import investment_mode as im
from global_markets.investment_mode import Candidate, InvestmentConfig, decide_market

CFG = InvestmentConfig()


def sig(f=0.0, r=0.0, fc=0.0, c=0.0, q=0.0, l=0.0, conf=0.6, **conf_over):
    base = {"fundamental": (f, conf), "risk": (r, conf), "forecast": (fc, conf),
            "comparison": (c, conf), "quality": (q, conf), "liquidity": (l, conf)}
    for agent, value in conf_over.items():
        base[agent] = (base[agent][0], value)
    return base


def cand(key, signals, exchange="X", sector=None, **kw):
    kw.setdefault("distress_status", "LOW_RISK")
    return Candidate(key=key, exchange=exchange, sector=sector, signals=signals, **kw)


def ladder(n=20, exchange="X", top=0.8, step=0.08, q=0.1, **kw):
    """n stocks with strictly decreasing fundamentals so the ranking is unambiguous (s00 best, last worst)."""
    return [cand(f"s{i:02d}", sig(f=top - step * i, fc=top / 2 - step * i / 2, q=q), exchange=exchange, **kw)
            for i in range(n)]


def calls(decisions):
    return {k: d.call for k, d in decisions.items()}


# ------------------------------------------------------------------ mode flag / config
def test_mode_defaults_to_conservative(monkeypatch):
    monkeypatch.delenv("DECISION_MODE", raising=False)
    assert im.decision_mode() == "conservative"
    assert im.decision_mode("garbage") == "conservative"
    assert im.decision_mode("INVESTMENT") == "investment"
    assert im.apply_decision_mode(ladder()) == {}


def test_mode_env_enables_investment(monkeypatch):
    monkeypatch.setenv("DECISION_MODE", "investment")
    assert len(im.apply_decision_mode(ladder())) == 20


def test_config_override_from_json_and_bad_input():
    cfg = im.load_config('{"buy_min_score": 0.5, "buy_top_fraction": 0.2, "unknown_key": 1}')
    assert cfg.buy_min_score == 0.5 and cfg.buy_top_fraction == 0.2
    assert im.load_config("not json") == im.DEFAULT_CONFIG
    assert im.load_config("") == im.DEFAULT_CONFIG


def test_thresholds_are_config_values_not_hard_coded():
    base = decide_market(ladder(20), CFG)
    wide = decide_market(ladder(20), InvestmentConfig(buy_top_fraction=0.5, accumulate_top_fraction=0.5))
    assert sum(d.call == "BUY" for d in base.values()) == 2
    assert sum(d.call == "BUY" for d in wide.values()) == 6      # capped by the 0.10 score floor, not by the fraction


# ------------------------------------------------------------------ (a) missing data = unknown
def test_missing_agent_is_excluded_not_zero():
    full = sig(f=0.6, r=0.6, fc=0.6, c=0.6, q=0.6, l=0.6)
    score, conf, n, used = im.known_score(dict(full, comparison=(0.0, 0.0)))
    assert n == 5 and "comparison" not in used
    assert score == pytest.approx(0.6) and conf == pytest.approx(0.6)


def test_abstaining_comparison_with_confidence_025_is_unknown():
    score, conf, n, used = im.known_score(dict(sig(f=0.5), comparison=(0.0, 0.25)))
    assert "comparison" not in used and n == 5


def test_confidence_reduced_only_below_four_agents():
    four = dict.fromkeys(["fundamental", "risk", "forecast", "quality"], (0.5, 0.6))
    three = dict.fromkeys(["fundamental", "forecast", "quality"], (0.5, 0.6))
    d4 = decide_market([cand(f"p{i}", four) for i in range(10)])
    d3 = decide_market([cand(f"p{i}", three) for i in range(10)])
    assert d4["p0"].confidence == pytest.approx(0.6)
    assert d3["p0"].confidence == pytest.approx(0.6 * 3 / 4)
    assert "few_agents" in d3["p0"].flags and "few_agents" not in d4["p0"].flags


def test_fewer_than_three_agents_is_hard_block():
    two = dict.fromkeys(["fundamental", "forecast"], (0.9, 0.7))
    d = decide_market([cand("a", two)] + ladder(10))
    assert d["a"].call == "NO_RECOMMENDATION" and "only 2 agent" in d["a"].blocked_by and "hard_block" in d["a"].flags


def test_hard_blocked_stock_does_not_shift_the_ranking():
    base = decide_market(ladder(20))
    extra = decide_market(ladder(20) + [cand("junk", dict.fromkeys(["fundamental", "risk"], (0.9, 0.9)))])
    assert {k: v.call for k, v in base.items()} == {k: extra[k].call for k in base}


# ------------------------------------------------------------------ (b) risk relative to the exchange
def risk_cand(i, vol, **kw):
    return cand(f"r{i:02d}", sig(f=0.2, r=-0.6), risk_metrics={"volatility_pct": vol, "drawdown_pct": -vol / 2}, **kw)


def test_risk_vote_is_percentile_median_is_zero():
    cs = [risk_cand(i, 10 + 5 * i) for i in range(21)]          # 21 stocks, volatility rises with i
    votes = im.relative_risk_votes(cs)
    assert votes["r10"] == pytest.approx(0.0, abs=0.01)         # median risk -> ~0
    assert votes["r00"] > 0.9 and votes["r20"] < -0.9           # calmest +, wildest -
    assert all(-1 <= v <= 1 for v in votes.values())


def test_risk_is_no_longer_structurally_negative():
    cs = [risk_cand(i, 40 + 2 * i) for i in range(30)]          # every raw risk vote is -0.6
    votes = list(im.relative_risk_votes(cs).values())
    assert sum(votes) / len(votes) == pytest.approx(0.0, abs=0.05)


def test_risk_uses_sector_cohort_when_at_least_eight_peers():
    calm = [risk_cand(i, 10 + i, sector="Utilities") for i in range(8)]
    wild = [risk_cand(100 + i, 80 + i, sector="Tech") for i in range(8)]
    votes = im.relative_risk_votes(calm + wild)
    assert max(votes[c.key] for c in wild) > 0.8                # the calmest tech stock is top of ITS sector
    assert min(votes[c.key] for c in calm) < -0.8               # the wildest utility is bottom of ITS sector


def test_risk_falls_back_to_exchange_when_sector_has_fewer_than_eight():
    small = [risk_cand(i, 10 + i, sector="Utilities") for i in range(7)]
    rest = [risk_cand(100 + i, 60 + i, sector=None) for i in range(10)]
    votes = im.relative_risk_votes(small + rest)
    assert votes["r00"] > 0.8 and votes["r106" if False else "r106"] < 0 < votes["r00"]


def test_risk_cohort_is_one_exchange():
    a = [risk_cand(i, 10 + i, exchange="A") for i in range(10)]
    b = [risk_cand(50 + i, 90 + i, exchange="B") for i in range(10)]
    votes = im.relative_risk_votes(a + b)
    assert votes["r00"] == pytest.approx(votes["r50"])          # both are the calmest of their own exchange


def test_risk_without_metrics_uses_raw_vote_percentile_and_no_data_is_excluded():
    cs = [cand(f"n{i}", sig(r=-0.5 + 0.1 * i)) for i in range(11)] + [cand("none", sig(r=0.0, conf=0.0))]
    votes = im.relative_risk_votes(cs)
    assert votes["n10"] > 0.8 and votes["n0"] < -0.8 and "none" not in votes


# ------------------------------------------------------------------ (c) comparison agent widening
def pe_cand(key, pe, exchange="X", sector="Tech", peers=None, raw=(0.0, 0.25), growth=None, isin=None, **kw):
    s = sig(f=0.2, q=0.2)
    s["comparison"] = raw
    return cand(key, s, exchange=exchange, sector=sector, pe=pe, peer_count=peers, growth_pct=growth, isin=isin, **kw)


def test_comparison_native_group_is_kept():
    c = pe_cand("a", 10.0, peers=12, raw=(0.35, 0.65))
    assert im.comparison_votes([c])["a"] == (0.35, 0.65, "scan_sector")


def test_comparison_widens_to_exchange_sector():
    peers = [pe_cand(f"p{i}", 20.0) for i in range(9)]
    target = pe_cand("t", 10.0, peers=2, raw=(0.0, 0.25))           # native group of 2: abstained
    vote, conf, scope = im.comparison_votes(peers + [target])["t"]
    assert scope == "exchange_sector" and vote == 0.6 and conf == CFG.comparison_confidence   # 50% discount


def test_comparison_widens_to_same_sector_in_all_markets():
    here = [pe_cand("t", 10.0, exchange="A", isin="T")]
    elsewhere = [pe_cand(f"o{i}", 20.0, exchange="B", isin=f"O{i}") for i in range(9)]
    vote, conf, scope = im.comparison_votes(here + elsewhere)["t"]
    assert scope == "global_sector" and vote == 0.6 and conf == CFG.comparison_confidence_global


def test_widening_can_be_switched_off():
    peers = [pe_cand(f"p{i}", 20.0) for i in range(9)]
    out = im.comparison_votes(peers + [pe_cand("t", 10.0)], InvestmentConfig(widen_peers=False))
    assert out["t"] == (None, 0.0, "none")


def test_global_pool_counts_one_row_per_isin():
    here = [pe_cand("t", 10.0, exchange="A", isin="T")]
    dup = [pe_cand(f"x{i}", 20.0, exchange="B", isin="SAME") for i in range(9)]      # one issuer listed 9 times
    assert im.comparison_votes(here + dup)["t"][2] == "none"


def test_comparison_small_group_and_none():
    t = pe_cand("t", 10.0, peers=4, raw=(0.35, 0.65))
    assert im.comparison_votes([t])["t"] == (0.35, 0.65, "small_group")
    assert im.comparison_votes([pe_cand("u", 10.0)])["u"] == (None, 0.0, "none")
    loss = pe_cand("l", None, raw=(0.1, 0.5))
    assert im.comparison_votes([loss])["l"] == (0.1, 0.5, "book_value")


def test_comparison_without_sector_cannot_widen():
    peers = [pe_cand(f"p{i}", 20.0) for i in range(9)]
    t = pe_cand("t", 10.0, sector=None)
    assert im.comparison_votes(peers + [t])["t"][2] == "none"


def test_comparison_blends_peg_where_growth_exists():
    peers = [pe_cand(f"p{i}", 20.0, growth=10.0) for i in range(9)]               # PEG 2.0
    cheap_pe_but_slow = pe_cand("slow", 14.0, growth=2.0)                         # P/E -30% discount, PEG 7 (premium)
    cheap_and_growing = pe_cand("fast", 14.0, growth=20.0)                        # P/E -30% discount, PEG 0.7
    out = im.comparison_votes(peers + [cheap_pe_but_slow, cheap_and_growing])
    assert out["fast"][0] > out["slow"][0]
    assert out["fast"][0] == pytest.approx((0.6 * 0 + 0.35 + 0.6) / 2) or out["fast"][0] > 0.3


def test_peg_ignores_nonpositive_growth_and_caps_growth():
    assert im.peg(pe_cand("a", 20.0, growth=-5.0), CFG) is None
    assert im.peg(pe_cand("a", 20.0, growth=400.0), CFG) == pytest.approx(20.0 / 50.0)
    assert im.peg(pe_cand("a", -3.0, growth=10.0), CFG) is None


def test_widened_comparison_feeds_the_score():
    peers = [pe_cand(f"p{i}", 20.0) for i in range(9)]
    d = decide_market(peers + [pe_cand("t", 10.0)])
    assert d["t"].peer_scope == "exchange_sector" and "peer_scope_exchange_sector" in d["t"].flags
    assert "comparison" in d["t"].used_votes


# ------------------------------------------------------------------ (d) relative tiers + floors
def test_tier_distribution_follows_fractions():
    d = decide_market(ladder(40, top=0.9, step=0.045))     # scores run from +0.9 down to about -0.85
    c = calls(d)
    assert [c[f"s{i:02d}"] for i in range(4)] == ["BUY"] * 4                       # top 10%
    assert all(c[f"s{i:02d}"] == "ACCUMULATE" for i in range(4, 10))               # 10-25%
    assert all(c[f"s{i:02d}"] == "SELL" for i in range(36, 40))                    # bottom 10%
    assert all(c[f"s{i:02d}"] == "REDUCE" for i in range(30, 36))                  # 10-25% from the bottom
    assert all(c[f"s{i:02d}"] == "HOLD" for i in range(10, 30))


def test_buy_requires_score_above_floor():
    d = decide_market(ladder(20, top=0.12, step=0.001))    # whole market scores ~0.06: top 10% fails > 0.10
    assert not any(v.call == "BUY" for v in d.values())
    assert d["s00"].call == "ACCUMULATE"                    # but > 0, so the next tier


def test_no_buy_or_accumulate_with_nonpositive_score():
    d = decide_market(ladder(20, top=-0.05, step=0.001, q=-0.05))   # every stock slightly negative
    assert not any(v.call in ("BUY", "ACCUMULATE") for v in d.values())
    assert all(v.score <= 0 for v in d.values())


def test_sell_requires_score_below_floor_and_reduce_below_zero():
    d = decide_market(ladder(20, top=0.30, step=0.001))    # all positive: the bottom tiers must stay HOLD
    assert not any(v.call in ("SELL", "REDUCE") for v in d.values())
    d = decide_market(ladder(20, top=-0.02, step=0.006, q=-0.02))   # bottom 10% around -0.05: REDUCE, not SELL
    assert not any(v.call == "SELL" for v in d.values())
    assert d["s19"].call == "REDUCE"


def test_tiers_are_recomputed_per_exchange():
    d = decide_market(ladder(20, exchange="A") + [
        cand(f"b{i:02d}", sig(f=0.8 - 0.08 * i, fc=0.4 - 0.04 * i, q=0.1), exchange="B") for i in range(20)])
    assert d["s00"].call == d["b00"].call == "BUY"
    assert sum(v.call == "BUY" for k, v in d.items() if k.startswith("s")) == 2
    assert sum(v.call == "BUY" for k, v in d.items() if k.startswith("b")) == 2


def test_small_market_gets_no_forced_buy():
    d = decide_market(ladder(5))
    assert not any(v.call == "BUY" for v in d.values())     # 10% of 5 rounds down to 0


# ------------------------------------------------------------------ (e) disagreement -> downgrade, not abstain
def test_disagreement_downgrades_buy_to_accumulate_with_flag():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9, c=-0.5, conf=0.7))
    d = decide_market(items)
    assert d["s00"].call == "ACCUMULATE"
    assert "agents_disagree" in d["s00"].flags and d["s00"].tier_before_flags == "BUY"


def test_disagreement_downgrades_sell_to_reduce():
    items = ladder(20)
    items[19] = cand("s19", sig(f=-0.9, fc=-0.9, q=-0.9, l=0.6, conf=0.7))
    d = decide_market(items)
    assert d["s19"].call == "REDUCE" and "agents_disagree" in d["s19"].flags


def test_disagreement_alone_never_gives_no_recommendation():
    items = [cand(f"k{i}", sig(f=0.9, c=-0.5, conf=0.7)) for i in range(20)]
    d = decide_market(items)
    assert all(v.call != "NO_RECOMMENDATION" for v in d.values())


# ------------------------------------------------------------------ (f) PR #52 gates = flags, hard blocks stay
def test_pr52_gates_are_downgrade_flags_not_blocks():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9), distress_status="ELEVATED_RISK")
    d = decide_market(items)
    assert d["s00"].call == "ACCUMULATE" and "distress_not_low_risk" in d["s00"].flags
    assert d["s00"].blocked_by is None


def test_comparison_only_positive_signal_flags_no_independent_signal():
    items = ladder(20)
    only_cmp = {"fundamental": (-0.1, 0.6), "risk": (-0.1, 0.6), "forecast": (-0.1, 0.6),
                "comparison": (0.6, 0.65), "quality": (-0.1, 0.6), "liquidity": (-0.1, 0.6)}
    items[0] = cand("s00", only_cmp)
    d = decide_market([i for i in items[1:]] + [items[0]])
    assert "no_independent_signal" in d["s00"].flags


def test_peer_group_below_eight_flag_downgrades_buy():
    items = ladder(20)
    items[0] = cand("s00", dict(items[0].signals, comparison=(0.35, 0.65)), pe=10.0, sector="Tech", peer_count=4)
    d = decide_market(items)
    assert d["s00"].peer_scope == "small_group" and "peer_group_small" in d["s00"].flags
    assert d["s00"].call == "ACCUMULATE"


def test_soft_flags_together_move_at_most_one_tier():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9, c=-0.5, conf=0.7), distress_status="ELEVATED_RISK")
    assert decide_market(items)["s00"].call == "ACCUMULATE"


def test_soft_flag_set_is_configurable():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9), distress_status="ELEVATED_RISK")
    d = decide_market(items, InvestmentConfig(soft_downgrade_flags=()))
    assert d["s00"].call == "BUY" and "distress_not_low_risk" in d["s00"].flags


def test_evidence_block_is_hard_block():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9), evidence_status="BLOCK")
    d = decide_market(items)
    assert d["s00"].call == "NO_RECOMMENDATION" and d["s00"].blocked_by == "evidence BLOCK"


def test_distress_positive_block_blocks_positive_tiers_only():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9), positive_block=True)
    items[19] = cand("s19", sig(f=-0.9, fc=-0.9, q=-0.9), positive_block=True)
    d = decide_market(items)
    assert d["s00"].call == "NO_RECOMMENDATION" and d["s00"].blocked_by == "distress positive_block"
    assert d["s19"].call == "SELL"                                 # a distressed stock can still be sold


def test_evidence_warn_flags_and_downgrades_buy():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9), evidence_status="WARN")
    d = decide_market(items)
    assert "evidence_warn" in d["s00"].flags and d["s00"].call == "ACCUMULATE"


# ------------------------------------------------------------------ (g) output
@pytest.mark.parametrize("conf,hint", [(0.9, "high"), (0.65, "high"), (0.64, "medium"), (0.5, "medium"), (0.49, "small")])
def test_position_size_hint(conf, hint):
    assert im.position_size_hint(conf) == hint


def test_reasons_are_top_two_positive_and_negative():
    used = {"fundamental": 0.8, "quality": 0.5, "forecast": 0.1, "risk": -0.6, "liquidity": -0.2, "comparison": -0.5}
    pos, neg = im.reasons(used, dict.fromkeys(used, 0.6))
    assert pos == ("fundamental (+0.80)", "quality (+0.50)")
    assert neg == ("risk (-0.60)", "comparison (-0.50)")


def test_decision_fields_are_complete():
    d = decide_market(ladder(20))["s00"]
    assert d.call == "BUY" and d.rank == 1 and d.percentile == 0.0 and d.agents_with_data == 6
    assert d.position_size_hint in ("high", "medium", "small")
    assert d.positive_reasons and d.peer_scope == "book_value" and d.reason.startswith("+ ")
    assert isinstance(d.flags, tuple)


# ------------------------------------------------------------------ (h) heavy missing data (Germany-like market)
def test_germany_like_market_still_produces_actionable_tiers():
    """98% of stocks below the conservative 0.55 confidence: comparison missing, cash-flow agents thin."""
    market = []
    for i in range(60):
        s = {"fundamental": (0.5 - 0.016 * i, 0.47), "risk": (-0.3, 0.4), "forecast": (0.3 - 0.01 * i, 0.5),
             "comparison": (0.0, 0.0), "quality": (0.4 - 0.012 * i, 0.45), "liquidity": (0.1, 0.5)}
        market.append(cand(f"de{i:02d}", s, exchange="XETRA"))
    d = decide_market(market)
    c = calls(d)
    assert sum(v == "BUY" for v in c.values()) == 6
    assert sum(v == "ACCUMULATE" for v in c.values()) == 9
    assert sum(v == "SELL" for v in c.values()) >= 1
    assert all(v.confidence < 0.55 and v.position_size_hint == "small" for v in d.values())   # honest, not abstaining
    assert all("comparison" not in v.used_votes for v in d.values())


# ------------------------------------------------------------------ stored results
RESULT = {
    "exchange": "NYSE", "ticker": "ALV", "isin": "US0000000001",
    "signals": [{"agent": "fundamental", "vote": 0.35, "confidence": 0.71}, {"agent": "risk", "vote": -0.05, "confidence": 0.78}],
    "evidence": {"status": "PASS", "confidence_multiplier": 0.98},
    "distress": {"status": "LOW_RISK", "positive_block": False},
    "company": {"sector": "Industrials", "pe": 11.9, "net_income": 735e6, "revenue_prev": 10390e6, "net_margin_prev_pct": 6.2,
                "revenue_yoy_pct": 4.09, "volatility_annualized_pct": 28.3, "max_drawdown_pct": -22.0,
                "total_liabilities": 6062e6, "total_equity": 2582e6, "current_assets": 4101e6, "current_liabilities": 3923e6,
                "raw_provider_fields": {"peer_pe_benchmark_scope": "same_sector_scan_median", "peer_pe_benchmark_count": 10}},
}


def test_candidate_from_result_extracts_fields():
    c = im.candidate_from_result(RESULT)
    assert c.key == "NYSE:ALV" and c.sector == "Industrials" and c.peer_count == 10
    assert c.evidence_multiplier == pytest.approx(0.98) and c.pe == pytest.approx(11.9)
    assert c.growth_pct == pytest.approx((735e6 / (10390e6 * 0.062) - 1) * 100)      # earnings growth wins over revenue
    assert c.risk_metrics["current_ratio"] == pytest.approx(4101 / 3923)
    assert im.candidate_from_result({"signals": []}) is None


def test_decide_ledger_is_read_only_and_uses_full_results():
    class FakeLedger:
        def full_results(self):
            for i in range(12):
                r = dict(RESULT, ticker=f"T{i}", signals=[
                    {"agent": a, "vote": 0.5 - 0.08 * i, "confidence": 0.6}
                    for a in ("fundamental", "risk", "forecast", "quality")])
                yield r
    d = im.decide_ledger(FakeLedger())
    assert len(d) == 12 and d["NYSE:T0"].call == "BUY"
