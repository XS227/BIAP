"""Agent 9 / Agent 10 wording and the single Zmijewski band (v2 follow-ups from the 0.3.24 phone test)."""
from global_markets import distress, decision_overlay


def test_zmijewski_bands_are_shared_and_48_8_percent_is_the_watch_band():
    assert distress.zmijewski_band(0.488) == "watch band (20-50%)"
    assert distress.zmijewski_band(0.05) == "distress-unlikely" and distress.zmijewski_band(0.5) == "distress-likely"


def test_risk_agent_is_labelled_market_risk():
    assert decision_overlay.AGENT_LABEL["risk"] == "Market risk"


def test_agent10_text_has_no_agency_wording():
    import inspect
    from global_markets import credit_scoring
    src = inspect.getsource(credit_scoring)
    assert "Moody's/S&P-style" not in src and "not a credit rating" not in src
