from global_markets.opportunity import (
    BUY, HIGH_RISK, INSUFFICIENT_DATA, REVIEW, WATCH, classify_opportunity, rank_opportunities,
)


def _gov(accepted=False, **kw):
    base = dict(accepted=accepted, hard_blocks=(), reasoning="", escalated=not accepted)
    base.update(kw)
    return base


def _ev(status="PASS", **kw):
    return {"status": status, "contradictions": (), "missing_critical": (), **kw}


def _dist(status="LOW_RISK", **kw):
    return {"status": status, "positive_block": False, "reasoning": "", "missing_inputs": (), **kw}


def _c(**kw):
    args = dict(preliminary_call="HOLD_OR_WATCH", final_call="NO_RECOMMENDATION", score=0.2,
                confidence=0.5, evidence=_ev(), distress=_dist(), governance=_gov())
    args.update(kw)
    return classify_opportunity(**args)


def test_qualified_buy_requires_acceptance():
    out = _c(preliminary_call="BUY_CANDIDATE", final_call="BUY_CANDIDATE", score=0.4, confidence=0.7,
             governance=_gov(accepted=True))
    assert out["state"] == BUY and out["agent8Abstention"] == []


def test_hold_or_watch_abstention_exposed_and_watch():
    out = _c()
    assert out["state"] == WATCH
    assert out["agent8Abstention"][0]["code"] == "NON_DIRECTIONAL_BELOW_ACCEPT_THRESHOLD"
    assert out["underlying"]["draftCall"] == "HOLD_OR_WATCH"


def test_missing_distress_inputs_never_high_risk_or_insufficient():
    out = _c(distress=_dist("INSUFFICIENT_DATA", missing_inputs=("total_debt", "ebitda")))
    assert out["state"] == WATCH
    assert out["distressAxis"]["dataGap"] is True


def test_high_risk_only_from_computed_distress_or_negative_score():
    assert _c(distress=_dist("HIGH_RISK"))["state"] == HIGH_RISK
    assert _c(preliminary_call="AVOID_OR_REVIEW", score=-0.4, confidence=0.6)["state"] == HIGH_RISK


def test_block_or_low_confidence_is_insufficient():
    assert _c(evidence=_ev("BLOCK", missing_critical=("verified_price",)))["state"] == INSUFFICIENT_DATA
    assert _c(confidence=0.2)["state"] == INSUFFICIENT_DATA


def test_warn_evidence_or_elevated_distress_routes_to_review():
    assert _c(evidence=_ev("WARN"))["state"] == REVIEW
    assert _c(distress=_dist("ELEVATED_RISK"))["state"] == REVIEW


def test_ranking_excludes_negative_and_unfit_states():
    def row(state, score, conf=0.5):
        return {"opportunity": {"state": state, "underlying": {"score": score, "confidence": conf}}}
    rows = [row(HIGH_RISK, 0.9), row(REVIEW, -0.1), row(REVIEW, 0.2), row(WATCH, 0.15), row(BUY, 0.3)]
    ranked = rank_opportunities(rows, 20)
    assert [r["opportunity"]["state"] for r in ranked] == [BUY, WATCH, REVIEW]


def test_accepted_hold_or_watch_is_watch():
    out = _c(final_call="HOLD_OR_WATCH", governance=_gov(accepted=True), score=0.08, confidence=0.57)
    assert out["state"] == WATCH and out["agent8Abstention"] == []


def test_single_model_high_risk_routes_to_review_but_corroborated_stays_high_risk():
    one = _c(distress=_dist("HIGH_RISK", available_models=("zmijewski",)), score=-0.1, confidence=0.46)
    assert one["state"] == REVIEW and one["primaryCause"] == "ELEVATED_DISTRESS_RISK"
    two = _c(distress=_dist("HIGH_RISK", available_models=("zmijewski", "altman")), score=-0.1, confidence=0.46)
    assert two["state"] == HIGH_RISK


def test_market_opportunities_never_pads_and_collapses_issuers():
    from global_markets.opportunity import market_opportunities

    def res(t, score, conf, accepted=False, call="NO_RECOMMENDATION", name=None):
        return {"ticker": t, "name": name or t, "country": "SE", "lei": "5493001KJTIIGC8Y1R12" if name else None, "call": call, "score": score, "confidence": conf,
                "decisionIntegrity": {"preliminaryCall": "HOLD_OR_WATCH"},
                "evidence": _ev(), "distress": _dist(), "governance": _gov(accepted=accepted), "signals": []}
    out = market_opportunities([res("ZZA", 0.2, 0.5, name="Atlas Copco A"), res("ZZB", 0.19, 0.5, name="Atlas Copco B"),
                                res("NEG", -0.2, 0.6, call="NO_RECOMMENDATION")], limit=20)
    assert len(out["ranked"]) == 1 and out["stateCounts"]["WATCH"] == 2
