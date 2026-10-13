"""Market Top 10 (any call, evidence-supported) is separate from Qualified BUY; gates are counted, never bypassed."""
from types import SimpleNamespace

import pytest

from global_markets import analysis_ledger as al
from global_markets.scanner import GlobalMarketScanner


def _result(ticker, *, call, score, confidence, evidence="PASS"):
    return {
        "ticker": ticker, "name": f"Co {ticker}", "country": "NO", "exchange": "EURONEXT_OSLO",
        "call": call, "score": score, "confidence": confidence,
        "evidence": {"status": evidence, "missing_critical": []},
        "fundamentalEvidence": {"fundamental_source": "official" if evidence == "PASS" else None},
        "company": {"ticker": ticker, "name": f"Co {ticker}", "country": "NO", "exchange": "EURONEXT_OSLO"},
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
