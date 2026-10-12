"""Behaviour of the persistent analysis queue that replaced the hidden 75-company cap."""
from types import SimpleNamespace

import pytest

from global_markets import analysis_ledger as al


def _company(i):
    return SimpleNamespace(ticker=f"T{i:03d}", name=f"Company {i}")


def _quote(i):
    return {"ticker": f"T{i:03d}", "liquidityValue": float(1000 - i)}


def _result(ticker, *, evidence="PASS", missing=(), call="HOLD", company=None, detail=""):
    return {
        "ticker": ticker, "call": call, "score": 0.5, "confidence": 0.6,
        "evidence": {"status": evidence, "missing_critical": list(missing), "official_fundamental_detail": detail},
        "fundamentalEvidence": {"fundamental_source": "SEC EDGAR" if evidence == "PASS" else None},
        "company": company or {},
    }


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    yield led
    led.close()


def _register(led, n, quoted=None):
    universe = [_company(i) for i in range(n)]
    quotes = {f"T{i:03d}": _quote(i) for i in range(n if quoted is None else quoted)}
    led.sync_universe(universe, quotes, screening_source="test feed")
    return {c.ticker: c for c in universe}


def _drain(led, universe, analyze, *, batch=500, budget=60.0):
    return al.drain(led, analyze, batch_limit=batch, time_budget_sec=budget, refresh_after_hours=24.0, universe_by_ticker=universe)


def test_every_company_is_analyzed_not_just_the_first_75(ledger):
    universe = _register(ledger, 403)
    assert ledger.counts()["queued"] == 403
    seen = []
    # many small batches, as a phone-driven + timer-driven system would do
    while ledger.counts()["queued"]:
        out = _drain(ledger, universe, lambda c: seen.append(c.ticker) or _result(c.ticker), batch=40)
        assert out["attempted"] <= 40
    assert len(seen) == len(set(seen)) == 403
    counts = ledger.counts()
    assert counts["byStatus"][al.COMPLETE] == 403 and counts["deepAnalyzed"] == 403 and counts["progressPct"] == 100.0


def test_least_liquid_company_is_still_reached(ledger):
    universe = _register(ledger, 200)
    _drain(ledger, universe, lambda c: _result(c.ticker), batch=75)
    row = ledger._conn().execute("SELECT status FROM ledger WHERE ticker='T199'").fetchone()
    assert row["status"] == al.PENDING  # liquid-first ordering, but queued not dropped
    _drain(ledger, universe, lambda c: _result(c.ticker), batch=75)
    _drain(ledger, universe, lambda c: _result(c.ticker), batch=75)
    assert ledger._conn().execute("SELECT status FROM ledger WHERE ticker='T199'").fetchone()["status"] == al.COMPLETE


def test_progress_survives_restart_and_crash_mid_analysis(ledger, tmp_path):
    universe = _register(ledger, 30)
    calls = {"n": 0}

    def crash_on_fifth(c):
        calls["n"] += 1
        if calls["n"] == 5:
            raise KeyboardInterrupt  # simulates kill: not an Exception, nothing is recorded
        return _result(c.ticker)

    with pytest.raises(KeyboardInterrupt):
        _drain(ledger, universe, crash_on_fifth)
    ledger.close()
    reopened = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")  # new process, same file
    try:
        counts = reopened.counts()
        assert counts["byStatus"][al.COMPLETE] == 4  # finished work was not lost
        assert counts["byStatus"][al.ANALYZING] == 1  # the in-flight one is visible, not silently done
        out = _drain(reopened, universe, lambda c: _result(c.ticker))
        assert out["ran"] and reopened.counts()["byStatus"][al.COMPLETE] == 30
        assert reopened.counts()["queued"] == 0
    finally:
        reopened.close()


def test_batch_and_time_budget_are_respected(ledger):
    universe = _register(ledger, 50)
    assert _drain(ledger, universe, lambda c: _result(c.ticker), batch=7)["attempted"] == 7
    out = _drain(ledger, universe, lambda c: _result(c.ticker), budget=0.0)
    assert out["attempted"] == 0 and out["budgetExhausted"] is True
    assert ledger.counts()["queued"] == 43


def test_second_worker_cannot_run_concurrently(ledger):
    universe = _register(ledger, 5)
    with ledger.worker_lock() as owned:
        assert owned
        other = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
        try:
            out = _drain(other, universe, lambda c: _result(c.ticker))
        finally:
            other.close()
    assert out["ran"] is False and ledger.counts()["queued"] == 5


def test_status_classification_has_reason_and_source():
    ok = al.classify_result(_result("A"))
    assert ok[0] == al.COMPLETE and ok[2] == "SEC EDGAR"
    absent = al.classify_result(_result("B", evidence="BLOCK", missing=["fundamental_source", "fundamental_core_figures"], detail="no ESEF filing found"))
    assert absent[0] == al.INSUFFICIENT_DATA and "fundamental_source" in absent[1] and "no ESEF filing" in absent[1]
    stale = al.classify_result(_result("C", evidence="BLOCK", missing=["fresh_fundamentals"]))
    assert stale[0] == al.BLOCKED and stale[1].startswith("gate_failed:fresh_fundamentals")


def test_company_without_quote_is_insufficient_data_with_reason_never_dropped(ledger):
    _register(ledger, 10, quoted=8)
    counts = ledger.counts()
    assert counts["total"] == 10 and counts["byStatus"][al.INSUFFICIENT_DATA] == 2
    assert "no_usable_market_quote_in_stage1_screen" in counts["insufficientReasons"]


def test_repeated_crash_ends_as_insufficient_data_with_cause(ledger):
    universe = _register(ledger, 1)

    def boom(_c):
        raise RuntimeError("upstream 500")

    for _ in range(al.MAX_ATTEMPTS):
        _drain(ledger, universe, boom)
    row = ledger._conn().execute("SELECT status, reason FROM ledger").fetchone()
    assert row["status"] == al.INSUFFICIENT_DATA and "upstream 500" in row["reason"]


def test_evidence_pass_is_not_financial_completeness(ledger):
    universe = _register(ledger, 2)
    thin = {"revenue": 10.0, "net_income": 1.0}
    full = {k: 1.0 for k in al._FINANCIAL_CORE}
    results = {"T000": _result("T000", company=thin), "T001": _result("T001", company=full)}
    _drain(ledger, universe, lambda c: results[c.ticker])
    counts = ledger.counts()
    assert counts["evidencePass"] == 2 and counts["financiallyComplete"] == 1
    assert counts["financialGaps"]  # lists exactly which figures are missing


def test_bank_is_not_penalised_for_missing_ebitda_and_nothing_is_invented():
    bank = {k: 1.0 for k in al._FINANCIAL_CORE if k not in al._FINANCIAL_CORE_EXEMPT}
    out = al.financial_completeness({"company": {**bank, "sector": "Banks"}, "creditScoring": {"entity_type": "bank"}})
    assert out["complete"] is True
    gap = al.financial_completeness({"company": {"revenue": 1.0}})
    assert "ebitda" in gap["missing"] and gap["complete"] is False


def test_buy_candidates_are_not_inflated_by_queue(ledger):
    universe = _register(ledger, 20)
    _drain(ledger, universe, lambda c: _result(c.ticker, call="HOLD"))
    assert ledger.counts()["buyQualified"] == 0
    assert list(ledger.full_results(buys_only=True)) == []


def test_buy_requires_evidence_pass(ledger):
    universe = _register(ledger, 2)
    res = {"T000": _result("T000", call="BUY_CANDIDATE"), "T001": _result("T001", call="BUY_CANDIDATE", evidence="BLOCK", missing=["fresh_price"])}
    _drain(ledger, universe, lambda c: res[c.ticker])
    assert ledger.counts()["buyQualified"] == 1


def test_universe_resync_keeps_finished_results_and_adds_new(ledger):
    universe = _register(ledger, 5)
    _drain(ledger, universe, lambda c: _result(c.ticker))
    more = [_company(i) for i in range(8)]
    ledger.sync_universe(more, {f"T{i:03d}": _quote(i) for i in range(8)}, screening_source="test feed")
    counts = ledger.counts()
    assert counts["byStatus"][al.COMPLETE] == 5 and counts["byStatus"][al.PENDING] == 3


def test_legacy_app_deep_limit_75_is_only_a_batch_hint():
    from global_routes import ScanRequest

    req = ScanRequest(country="SE", exchange="NASDAQ_STOCKHOLM", deepLimit=75)
    assert req.deepLimit == 75 and req.batchLimit == 10


def test_financial_completeness_is_tiered_so_missing_ffo_does_not_hide_full_statements():
    core = {k: 1.0 for k in al._TIER_CORE}
    out = al.financial_completeness({"company": {**core, "market_cap": 5.0, "pe": 10.0}})
    assert out["coreComplete"] and out["valuationComplete"]
    assert out["creditComplete"] is False and out["complete"] is False  # EBITDA/debt/interest absent, not invented
    assert "ebitda" in out["missing"]
    no_valuation = al.financial_completeness({"company": core})
    assert no_valuation["coreComplete"] is True and no_valuation["valuationComplete"] is False
    assert no_valuation["valuationMissing"] == ["market_cap", "pe"]


def test_every_missing_figure_gets_a_cause_and_no_value_is_filled():
    core = {k: 1.0 for k in al._TIER_CORE}
    result = {
        "company": {**core, "price": 100.0, "currency": "SEK", "reporting_currency": "EUR", "eps": 2.0},
        "fundamentalEvidence": {"fundamental_source": "official-oam-se-fi-finanscentralen"},
        "creditScoring": {"factors_missing": {"debt_ebitda": "missing ebitda, total_debt"}},
    }
    out = al.financial_completeness(result)
    assert out["missingReasons"]["market_cap"].startswith("no_share_count")
    assert out["missingReasons"]["pe"].startswith("cross_currency_listing")
    assert out["missingReasons"]["ebitda"] == "absent_from_source:official-oam-se-fi-finanscentralen"
    assert out["missingReasons"]["ev_ebitda"] == "no_ebitda"
    assert out["creditRatioReasons"] == {"debt_ebitda": "missing ebitda, total_debt"}
    assert set(out["missingReasons"]) == set(out["missing"])
    assert result["company"].get("market_cap") is None  # nothing was invented
    withheld = al.financial_completeness({"company": {**core, "price": 1.0, "shares_outstanding": 5.0,
        "raw_provider_fields": {"derived_metrics": ["shares_withheld:inconsistent_with_net_income_over_eps(shares=5,implied=20)"]}}})
    assert withheld["missingReasons"]["market_cap"].startswith("share_count_withheld")


_DROPPED = "primary fundamentals unavailable (KAP request failed: RemoteProtocolError)"


def _dropped(ticker):
    return _result(ticker, evidence="BLOCK", missing=["fundamental_source"], detail=_DROPPED)


def test_transient_connection_drop_is_retried_not_recorded_as_a_data_verdict(ledger):
    universe = _register(ledger, 1)
    calls = []

    def flaky(company):
        calls.append(company.ticker)
        return _dropped(company.ticker) if len(calls) < 2 else _result(company.ticker)

    _drain(ledger, universe, flaky)
    row = ledger._conn().execute("SELECT status, reason, attempts FROM ledger").fetchone()
    assert row["status"] == al.PENDING and "retry_transient_source_error" in row["reason"] and row["attempts"] == 1
    assert len(calls) == 1  # not hammered again inside the same run
    _drain(ledger, universe, flaky)
    row = ledger._conn().execute("SELECT status, attempts FROM ledger").fetchone()
    assert row["status"] == al.COMPLETE and row["attempts"] == 0


def test_persistent_connection_drop_ends_terminal_with_cause_after_max_attempts(ledger):
    universe = _register(ledger, 1)
    for _ in range(al.MAX_ATTEMPTS):
        _drain(ledger, universe, lambda c: _dropped(c.ticker))
    row = ledger._conn().execute("SELECT status, reason FROM ledger").fetchone()
    assert row["status"] == al.INSUFFICIENT_DATA and "source_unreachable_after_3_attempts" in row["reason"]
    assert ledger.requeue_transient() == 0  # exhausted rows wait for the normal refresh window


def test_http_status_and_absent_data_are_never_treated_as_transient(ledger):
    universe = _register(ledger, 2)
    verdicts = {
        "T000": _result("T000", evidence="BLOCK", missing=["fundamental_source"], detail="SEC request failed: HTTPStatusError"),
        "T001": _result("T001", evidence="BLOCK", missing=["fundamental_source"], detail="no official financial-statement source attached"),
    }
    _drain(ledger, universe, lambda c: verdicts[c.ticker])
    counts = ledger.counts()
    assert counts["byStatus"][al.INSUFFICIENT_DATA] == 2 and counts["queued"] == 0


def test_requeue_transient_recovers_rows_recorded_before_the_fix(ledger):
    universe = _register(ledger, 2)
    ledger.record_result("T000", _result("T000"))
    ledger.record_result("T001", _result("T001", evidence="BLOCK", missing=["fundamental_source"], detail="no official financial-statement source attached"))
    ledger._conn().execute(
        "UPDATE ledger SET status=?, reason=?, attempts=0 WHERE ticker='T000'",
        (al.BLOCKED, "gate_failed:fresh_fundamentals (KAP request failed: RemoteProtocolError)"),
    )
    assert ledger.requeue_transient() == 1
    rows = {r["ticker"]: r["status"] for r in ledger._conn().execute("SELECT ticker, status FROM ledger")}
    assert rows == {"T000": al.PENDING, "T001": al.INSUFFICIENT_DATA}
    assert al.is_transient_failure("x request failed: ReadTimeout") and not al.is_transient_failure("request failed: HTTPStatusError")
