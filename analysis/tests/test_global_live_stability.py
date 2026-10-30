"""Live-stability guards: append-only analysis history, daily guard, manual-only deploy workflow."""
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from global_markets import analysis_ledger as al
from global_markets import daily_guard as dg

ROOT = Path(__file__).resolve().parents[2]


def _result(ticker, *, call="HOLD", score=0.5, evidence="PASS"):
    return {"ticker": ticker, "call": call, "score": score, "confidence": 0.6,
            "evidence": {"status": evidence, "missing_critical": [], "reasoning": "r"},
            "fundamentalEvidence": {"fundamental_source": "SEC EDGAR"}, "company": {}}


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BIAP_ENGINE_COMMIT", "abc1234")
    monkeypatch.setattr(al, "_ENGINE_COMMIT", None)
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    led._conn().execute("INSERT INTO ledger(ticker,name,status) VALUES('AAA','A','PENDING')")
    yield led
    led.close()


def test_reanalysis_keeps_every_previous_analysis(ledger):
    ledger.record_result("AAA", _result("AAA", call="BUY", score=0.9))
    ledger.record_result("AAA", _result("AAA", call="SELL", score=-0.4, evidence="BLOCK"))
    latest = ledger._conn().execute("SELECT call, score FROM ledger WHERE ticker='AAA'").fetchone()
    assert (latest["call"], latest["score"]) == ("SELL", -0.4)
    rows = ledger._conn().execute("SELECT call, score, evidence_status, engine_commit, flags, evidence "
                                  "FROM analysis_history WHERE ticker='AAA' ORDER BY id").fetchall()
    assert [(r["call"], r["score"]) for r in rows] == [("BUY", 0.9), ("SELL", -0.4)]
    assert rows[0]["evidence_status"] == "PASS" and rows[1]["evidence_status"] == "BLOCK"
    assert rows[0]["engine_commit"] == "abc1234"
    assert "reason" in json.loads(rows[0]["flags"]) and json.loads(rows[0]["evidence"])["status"] == "PASS"


def test_history_is_append_only(ledger):
    ledger.record_result("AAA", _result("AAA"))
    for sql in ("UPDATE analysis_history SET call='X'", "DELETE FROM analysis_history"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            ledger._conn().execute(sql)
    assert ledger._conn().execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0] == 1


def test_guard_flags_zero_buy_sell_and_block_rise():
    ok = {"BUY": 5, "SELL": 2, "BLOCK": 100}
    assert dg.evaluate({"A": ok}, {"A": {"BLOCK": 100}}) == []
    assert dg.evaluate({"A": {**ok, "BLOCK": 120}}, {"A": {"BLOCK": 100}}) == []          # exactly +20% is allowed
    assert any("BLOCK rose" in p for p in dg.evaluate({"A": {**ok, "BLOCK": 121}}, {"A": {"BLOCK": 100}}))
    out = dg.evaluate({"A": {"BUY": 0, "SELL": 0, "BLOCK": 1}, "B": None}, None)
    assert "A: BUY count is 0" in out and "A: SELL count is 0" in out and any("B: UNREADABLE" in p for p in out)


def test_guard_run_exit_codes_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GUARD_MARKETS", "X:ONE Y:TWO")
    sent = []
    mail = lambda subject, body: sent.append(body) or True
    good = lambda code: {"BUY": 3, "SELL": 1, "BLOCK": 10}
    assert dg.run_guard(good, date(2026, 10, 29), tmp_path, mail) == 0 and not sent
    worse = lambda code: {"BUY": 3, "SELL": 0 if code == "Y:TWO" else 1, "BLOCK": 20}
    assert dg.run_guard(worse, date(2026, 10, 30), tmp_path, mail) == 1
    assert "Y:TWO: SELL count is 0" in sent[0] and "X:ONE: BLOCK rose 10 -> 20" in sent[0]
    assert json.loads((tmp_path / "2026-10-30.json").read_text())["X:ONE"]["BLOCK"] == 20


def test_alert_logs_only_without_sendmail():
    assert dg.send_alert("s", "b", which=lambda _: None) is False
    calls = []
    assert dg.send_alert("s", "b", which=lambda _: "/usr/sbin/sendmail", run=lambda *a, **k: calls.append((a, k))) is True
    assert b"nasrindadashiwin@gmail.com" in calls[0][1]["input"]


def test_deploy_backend_is_manual_only():
    text = (ROOT / ".github/workflows/deploy-backend.yml").read_text()
    on_block = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert "workflow_dispatch" in on_block
    assert not re.search(r"^\s*(push|workflow_run|pull_request|schedule):", on_block, re.M)
    assert "environment: production" in text


def test_guard_skips_out_of_scope_but_flags_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GUARD_MARKETS", "X:ONE Y:OFF Z:BAD")

    def collect(code):
        if code == "Y:OFF":
            raise dg.OutOfScope(code)
        if code == "Z:BAD":
            raise RuntimeError("boom")
        return {"BUY": 1, "SELL": 1, "BLOCK": 0}

    sent = []
    assert dg.run_guard(collect, date(2026, 10, 30), tmp_path, lambda s, b: sent.append(b) or True) == 1
    assert "Z:BAD: UNREADABLE" in sent[0] and "Y:OFF" not in sent[0]


def test_collect_fails_when_investment_mode_off(monkeypatch):
    monkeypatch.setenv("DECISION_MODE", "conservative")
    with pytest.raises(RuntimeError, match="investment mode is off"):
        dg.collect_market("US:NASDAQ")
