"""Market Top 10 (any call, evidence-supported) is separate from Qualified BUY; gates are counted, never bypassed."""
from types import SimpleNamespace

import pytest

from global_markets import analysis_ledger as al
from global_markets.scanner import GlobalMarketScanner


_CORE = {
    "revenue": 1.0, "operating_income": 1.0, "net_income": 1.0, "total_assets": 1.0, "total_equity": 1.0,
    "operating_cash_flow": 1.0, "ebitda": 1.0, "total_debt": 1.0, "interest_expense": 1.0, "free_cash_flow": 1.0,
    "market_cap": 1.0, "pe": 1.0, "ev_ebitda": 1.0,
}


def _result(ticker, *, call, score, confidence, evidence="PASS", core=True):
    return {
        "ticker": ticker, "name": f"Co {ticker}", "country": "NO", "exchange": "EURONEXT_OSLO",
        "call": call, "score": score, "confidence": confidence,
        "evidence": {"status": evidence, "missing_critical": []},
        "fundamentalEvidence": {"fundamental_source": "official" if evidence == "PASS" else None},
        "company": {
            "ticker": ticker, "name": f"Co {ticker}", "country": "NO", "exchange": "EURONEXT_OSLO",
            **(_CORE if core else {}),
        },
    }


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = al.AnalysisLedger("NO", "EURONEXT_OSLO")
    rows = [
        ("AAA", "HOLD_OR_WATCH", 0.30, 0.60, "PASS"),
        ("BBB", "NO_RECOMMENDATION", 0.35, 0.40, "PASS"),
        ("CCC", "BUY_CANDIDATE", 0.40, 0.70, "PASS"),
        ("DDD", "NO_RECOMMENDATION", 0.90, 0.90, "BLOCK"),   # best raw numbers but evidence BLOCK: must never rank
        ("EEE", "NO_RECOMMENDATION", None, None, "BLOCK"),
    ]
    led.sync_universe([SimpleNamespace(ticker=r[0], name=r[0]) for r in rows], {}, screening_source="t")
    for t, call, s, c, ev in rows:
        res = _result(t, call=call, score=s, confidence=c, evidence=ev)
        led.record_result(t, res)
    yield led
    led.close()


def test_market_top10_ranks_any_call_but_never_blocked_evidence(ledger):
    top = GlobalMarketScanner.market_top10(ledger.market_pool(limit=50), 10)
    assert [r["ticker"] for r in top] == ["CCC", "AAA", "BBB"]
    assert "DDD" not in {r["ticker"] for r in top}
    assert [r["call"] for r in top] == ["BUY_CANDIDATE", "HOLD_OR_WATCH", "NO_RECOMMENDATION"]
    assert [r["qualifiedBuy"] for r in top] == [True, False, False]  # no BUY manufactured to fill the list


def test_thin_evidence_pass_is_never_ranked_but_a_buy_always_is(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = al.AnalysisLedger("NO", "EURONEXT_OSLO")
    rows = [("FULL", "HOLD_OR_WATCH", 0.2, 0.6, True), ("THIN", "NO_RECOMMENDATION", 0.9, 0.9, False), ("BUYT", "BUY_CANDIDATE", 0.1, 0.6, False)]
    led.sync_universe([SimpleNamespace(ticker=r[0], name=r[0]) for r in rows], {}, screening_source="t")
    for t, call, sc, c, core in rows:
        led.record_result(t, _result(t, call=call, score=sc, confidence=c, core=core))
    top = GlobalMarketScanner.market_top10(led.market_pool(limit=50), 10)
    assert [r["ticker"] for r in top] == ["FULL", "BUYT"]  # THIN has the best raw numbers but no core statements
    gates = led.ranking_gate_counts()
    assert gates["rankingEligible"] == 2
    g = GlobalMarketScanner.ranking_groups(gates)
    assert g["INSUFFICIENT_EVIDENCE"] == 1 and sum(g.values()) == 3
    funnel = {x["gate"]: x for x in GlobalMarketScanner.ranking_gates(gates, buy_after_issuer=1, ranking_eligible=True, readiness_reasons=[])}
    assert funnel["ranking_evidence_standard"]["rejected"] == 1
    note = GlobalMarketScanner.market_top_note(top, 10, gates, True)
    assert "Only 2 of the 10" in note and "no slot is filled with an unsupported company" in note
    led.close()


def test_gate_funnel_counts_every_company_and_reason(ledger):
    gates = GlobalMarketScanner.ranking_gates(
        ledger.ranking_gate_counts(), buy_after_issuer=1, ranking_eligible=True, readiness_reasons=[]
    )
    by = {g["gate"]: g for g in gates}
    assert by["evidence_pass"]["entered"] == 5 and by["evidence_pass"]["passed"] == 3 and by["evidence_pass"]["rejected"] == 2
    assert by["evidence_pass"]["byEvidenceStatus"] == {"BLOCK": 2}
    assert by["buy_threshold"]["passed"] == 1 and by["buy_threshold"]["rejected"] == 2
    assert by["buy_threshold"]["reasons"] == {"call=HOLD_OR_WATCH": 1, "call=NO_RECOMMENDATION": 1}
    for g in gates:
        assert g["entered"] == g["passed"] + g["rejected"]


def test_blocked_market_reports_the_blocking_reason_at_the_first_gate(ledger):
    gates = GlobalMarketScanner.ranking_gates(
        ledger.ranking_gate_counts(), buy_after_issuer=1, ranking_eligible=False,
        readiness_reasons=["official_fundamental_coverage_below_threshold"],
    )
    first = gates[0]
    assert first["gate"] == "market_ranking_released" and first["passed"] == 0
    assert first["reasons"] == {"official_fundamental_coverage_below_threshold": 5}


def test_groups_partition_every_company_and_label_categories(ledger):
    g = GlobalMarketScanner.ranking_groups(ledger.ranking_gate_counts())
    assert g == {"QUALIFIED_BUY": 1, "WATCHLIST_HOLD": 1, "AVOID_REVIEW": 0, "NO_SIGNAL": 1, "INSUFFICIENT_EVIDENCE": 2, "NOT_YET_ANALYZED": 0}
    assert sum(g.values()) == 5
    top = GlobalMarketScanner.market_top10(ledger.market_pool(limit=50), 10)
    assert [r["category"] for r in top] == ["QUALIFIED_BUY", "WATCHLIST_HOLD", "NO_SIGNAL"]


def test_german_share_classes_collapse_to_one_issuer():
    from global_markets.issuer import issuer_key_of

    key = lambda name: issuer_key_of({"name": name, "country": "DE"})
    assert key("FUCHS SE  NA ST O.N.") == key("FUCHS SE  VZO NA O.N.")
    assert key("VOLKSWAGEN AG ST O.N.") == key("VOLKSWAGEN AG VZO O.N.")
    assert key("SIEMENS AG  NA O.N.") != key("SIEMENS ENERGY AG NA O.N.")  # different legal entities stay apart


def test_partial_discovery_slice_never_shrinks_the_ledger_universe(tmp_path, monkeypatch):
    """A bounded probe (discoveryLimit=250) once flagged 2,763 of 3,013 NASDAQ rows out of the universe."""
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = al.AnalysisLedger("US", "NASDAQ")
    full = [SimpleNamespace(ticker=t, name=t) for t in ("AAA", "BBB", "CCC", "DDD")]
    led.sync_universe(full, {}, screening_source="full")
    assert led.counts()["total"] == 4

    led.sync_universe(full[:2], {}, screening_source="probe", demote_missing=False)
    assert led._conn().execute("SELECT COUNT(*) FROM ledger WHERE in_universe=1").fetchone()[0] == 4

    led.sync_universe(full[:2], {}, screening_source="full-but-shrunk")  # an authoritative full sync still demotes
    assert led._conn().execute("SELECT COUNT(*) FROM ledger WHERE in_universe=1").fetchone()[0] == 2
    led.close()
