"""P1.12 (v2 only): the liquidity agent no longer votes; tradability is a gate.

Owner decisions 2026-11-02:
1. The directional liquidity vote is removed (v2 only; v1 untouched).
2. Gate: daily traded value in USD (ECB rate) below 100k -> BUY / ACCUMULATE capped at HOLD, label "low liquidity".
   SELL / REDUCE are left alone.
3. DE: gate was off until the Xetra volume field was verified; verified 2026-11-02 (P2.1) against Deutsche Boerse's
   official post-trade file, so it is active like every other market.
4. Unknown liquidity (e.g. Norway) is not rejected: label "liquidity unconfirmed", BUY capped at ACCUMULATE.
"""
import pytest

from global_markets import decision_logic as dl
from global_markets import decision_overlay as ov
from global_markets import investment_mode as im
from global_markets.investment_mode import Candidate, decide_market


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(im.SCOPE_ENV, "all")
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")


def sig(f=0.0, r=0.0, fc=0.0, c=0.0, q=0.0, l=0.42, conf=0.6):
    return {"fundamental": (f, conf), "risk": (r, conf), "forecast": (fc, conf), "comparison": (c, conf),
            "quality": (q, conf), "liquidity": (l, conf)}


def ladder(n=20, exchange="US:NASDAQ", value=5_000_000.0, **kw):
    return [Candidate(key=f"s{i:02d}", exchange=exchange, sector=None, distress_status="LOW_RISK", daily_value_usd=value,
                      signals=sig(f=0.8 - 0.08 * i, fc=0.4 - 0.04 * i, q=0.1), **kw) for i in range(n)]


def with_value(cands, key, value):
    import dataclasses
    return [dataclasses.replace(c, daily_value_usd=value) if c.key == key else c for c in cands]


def test_liquidity_vote_does_not_count_in_v2():
    low = decide_market(ladder())
    high_vote = [__import__("dataclasses").replace(c, signals={**c.signals, "liquidity": (0.9, 0.9)}) for c in ladder()]
    other = decide_market(high_vote)
    assert {k: d.score for k, d in low.items()} == {k: d.score for k, d in other.items()}
    assert "liquidity" not in low["s00"].used_votes


def test_liquidity_vote_still_counts_in_v1(monkeypatch):
    import dataclasses
    monkeypatch.delenv("DECISION_LOGIC_VERSION")
    a = decide_market(ladder())
    b = decide_market([dataclasses.replace(c, signals={**c.signals, "liquidity": (-0.9, 0.9)}) for c in ladder()])
    assert {k: d.score for k, d in a.items()} != {k: d.score for k, d in b.items()}
    assert not any("low_liquidity" in d.flags or "liquidity_unconfirmed" in d.flags for d in a.values())


def test_low_value_caps_buy_and_accumulate_at_hold():
    base = ladder()
    assert base and decide_market(base)["s00"].call == "BUY"
    d = decide_market(with_value(with_value(base, "s00", 99_999.0), "s03", 10.0))
    assert d["s00"].call == "HOLD" and "low_liquidity" in d["s00"].flags
    assert d["s03"].call == "HOLD" and "low_liquidity" in d["s03"].flags
    gate = ov.payload(d["s00"])["blockingGate"]
    assert gate["code"] == "LOW_LIQUIDITY" and gate["from"] == "BUY" and gate["to"] == "HOLD"
    assert gate["labelFa"] == "نقدشوندگی کم"


def test_exactly_100k_passes():
    d = decide_market(with_value(ladder(), "s00", 100_000.0))
    assert d["s00"].call == "BUY" and "low_liquidity" not in d["s00"].flags


def test_sell_and_reduce_are_untouched_by_low_value():
    base = decide_market(ladder())
    worst = max(base, key=lambda k: base[k].rank)
    low = decide_market(with_value(ladder(), worst, 1.0))
    assert low[worst].call == base[worst].call
    assert "low_liquidity" not in low[worst].flags


def test_unknown_value_is_not_rejected_buy_becomes_accumulate_with_label():
    d = decide_market(with_value(ladder(), "s00", None))
    assert d["s00"].call == "ACCUMULATE" and "liquidity_unconfirmed" in d["s00"].flags
    gate = ov.payload(d["s00"])["blockingGate"]
    assert gate["code"] == "LIQUIDITY_UNCONFIRMED" and gate["to"] == "ACCUMULATE"
    assert gate["labelFa"] == "نقدشوندگی تأیید نشده"
    # an ACCUMULATE with unknown liquidity stays ACCUMULATE (labelled, not rejected)
    acc = decide_market(with_value(ladder(), "s03", None))["s03"]
    assert acc.call == "ACCUMULATE" and "liquidity_unconfirmed" in acc.flags


def test_unknown_value_leaves_sell_and_hold_alone():
    base = decide_market(ladder())
    worst = max(base, key=lambda k: base[k].rank)
    d = decide_market(with_value(ladder(), worst, None))
    assert d[worst].call == base[worst].call and "liquidity_unconfirmed" not in d[worst].flags


def test_germany_gate_is_active_after_xetra_volume_verification():
    base = decide_market(ladder(exchange="DE:XETRA"))
    low = decide_market(with_value(ladder(exchange="DE:XETRA"), "s00", 1.0))
    unknown = decide_market(with_value(ladder(exchange="DE:XETRA"), "s00", None))
    assert base["s00"].call == "BUY"
    assert low["s00"].call == "HOLD" and "low_liquidity" in low["s00"].flags
    assert unknown["s00"].call == "ACCUMULATE" and "liquidity_unconfirmed" in unknown["s00"].flags


def test_v1_has_no_gate(monkeypatch):
    monkeypatch.delenv("DECISION_LOGIC_VERSION")
    d = decide_market(with_value(ladder(), "s00", 1.0))
    assert d["s00"].call == "BUY"


# ---- value conversion ------------------------------------------------------------------------------------------------
class FakeFX:
    def rate(self, base, quote, on):
        table = {("NOK", "USD"): 0.1, ("EUR", "USD"): 1.1, ("USD", "USD"): 1.0, ("GBP", "USD"): 1.3}
        if (base, quote) not in table:
            raise dl_error()
        return type("Q", (), {"rate": table[(base, quote)]})()


def dl_error():
    from global_markets.providers import GlobalProviderError
    return GlobalProviderError("no rate")


def test_daily_value_usd_converts_with_ecb_rate():
    v = dl.daily_value_usd(price=100.0, avg_volume=2_000.0, currency="NOK", on="2026-10-30", fx=FakeFX())
    assert v == pytest.approx(100.0 * 2000.0 * 0.1)


def test_daily_value_usd_minor_unit_and_unknowns():
    assert dl.daily_value_usd(price=13000.0, avg_volume=1000.0, currency="GBX", on="2026-10-30", fx=FakeFX()) == pytest.approx(13000 * 1000 / 100 * 1.3)
    assert dl.daily_value_usd(price=1.0, avg_volume=None, currency="USD", on="2026-10-30", fx=FakeFX()) is None
    assert dl.daily_value_usd(price=1.0, avg_volume=0, currency="USD", on="2026-10-30", fx=FakeFX()) is None
    assert dl.daily_value_usd(price=None, avg_volume=5, currency="USD", on="2026-10-30", fx=FakeFX()) is None
    assert dl.daily_value_usd(price=1.0, avg_volume=5, currency="XXX", on="2026-10-30", fx=FakeFX()) is None
    assert dl.daily_value_usd(price=1.0, avg_volume=5, currency="USD", on="not-a-date", fx=FakeFX()) is None


def test_candidate_from_result_fills_daily_value_usd(monkeypatch):
    monkeypatch.setattr(im, "_fx_provider", lambda: FakeFX())
    result = {"exchange": "NO:EURONEXT_OSLO", "ticker": "AAA", "signals": [
        {"agent": "fundamental", "vote": 0.5, "confidence": 0.6}, {"agent": "liquidity", "vote": 0.42, "confidence": 0.6}],
        "company": {"price": 100.0, "avg_volume_30d": 2000.0, "currency": "NOK", "price_observed_at": "2026-10-30"},
        "evidence": {}, "distress": {}}
    c = im.candidate_from_result(result)
    assert c.daily_value_usd == pytest.approx(20_000.0)
    assert c.signals["liquidity"] == (0.42, 0.6)        # stored vote kept for display; the engine zeroes it in v2


def test_sell_margin_default_is_zero_so_production_sell_gate_is_unchanged():
    assert dl.SELL_NEGATIVE_MARGIN == 0.0
