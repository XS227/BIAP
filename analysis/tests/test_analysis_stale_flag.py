from global_markets.decision_overlay import analysis_staleness


def test_newer_price_flags_stale():
    out = analysis_staleness("2026-10-30T20:00:00+00:00", "2026-11-02")
    assert out["analysisStale"] is True and out["analysisStaleDays"] == 3 and out["priceAsOf"] == "2026-11-02"


def test_same_day_or_older_price_is_not_flagged():
    assert analysis_staleness("2026-10-30T20:00:00+00:00", "2026-10-30T16:30:00+00:00") is None
    assert analysis_staleness("2026-10-30T20:00:00+00:00", "2026-10-29") is None


def test_undated_side_is_not_flagged():
    assert analysis_staleness(None, "2026-11-02") is None
    assert analysis_staleness("2026-10-30T20:00:00Z", None) is None
    assert analysis_staleness("garbage", "2026-11-02") is None


def test_stale_label_flag_defaults_off(monkeypatch):
    from global_markets.session_calendar import flag_enabled
    monkeypatch.delenv("BIAP_ANALYSIS_STALE_LABEL", raising=False)
    assert flag_enabled("BIAP_ANALYSIS_STALE_LABEL") is False
    monkeypatch.setenv("BIAP_ANALYSIS_STALE_LABEL", "1")
    assert flag_enabled("BIAP_ANALYSIS_STALE_LABEL") is True
