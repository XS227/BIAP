from datetime import datetime, timezone

import kiasha_auto_invest as kai
from audit_store import AuditStore
from deadline import DeadlineExceeded
from kiasha import Decision
from kiasha_ai import KiashaAIProposal
from kiasha_auto_invest import AutoInvestStore
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore


def test_auto_invest_defaults_off(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    status = store.get_settings(user_id="u1")
    assert status["enabled"] is False
    assert status["horizon"] == "short"
    assert status["maxDailyTrades"] == 3


def test_auto_invest_update_is_user_scoped(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    changed = store.update_settings(user_id="u1", enabled=True, horizon="long", max_daily_trades=2)
    untouched = store.get_settings(user_id="u2")
    assert changed["enabled"] is True
    assert changed["horizon"] == "long"
    assert changed["maxDailyTrades"] == 2
    assert untouched["enabled"] is False
    assert untouched["maxDailyTrades"] == 3
    assert store.enabled_users() == ["u1"]


def test_auto_invest_claim_once_per_tehran_day(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    now = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)
    first = store.claim_today(user_id="u1", now_utc=now)
    second = store.claim_today(user_id="u1", now_utc=now)
    assert first is not None
    assert second is None
    store.finish(run_id=first, status="COMPLETED", result={"status": "COMPLETED"})
    assert store.claim_today(user_id="u1", now_utc=now) is None
    latest = store.latest_run(user_id="u1")
    assert latest is not None
    assert latest["status"] == "COMPLETED"


def test_auto_invest_retryable_run_can_reclaim_same_day(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    now = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)
    first = store.claim_today(user_id="u1", now_utc=now)
    assert first is not None
    store.finish(
        run_id=first,
        status="RETRYABLE",
        result={"status": "RETRYABLE", "trades": [], "liveExecution": False},
    )

    retried = store.claim_today(user_id="u1", now_utc=now)
    assert retried == first
    latest = store.latest_run(user_id="u1")
    assert latest is not None
    assert latest["status"] == "RUNNING"
    assert latest["finishedAt"] is None
    assert latest["result"] is None


def test_one_candidate_timeout_does_not_stop_others(monkeypatch):
    """A DeadlineExceeded on one candidate (simulated TSETMC/CODAL/AI stall)
    must be recorded as a retryable diagnostic and never prevent a later,
    healthy candidate from still being ranked."""
    monkeypatch.setattr(kai, "_candidate_symbols", lambda: ["TIMEOUT_CODE", "GOOD_CODE"])

    def fake_verified_company_bounded(code):
        if code == "TIMEOUT_CODE":
            raise DeadlineExceeded("simulated TSETMC stall")
        return ({"ticker": code}, 1000.0)

    monkeypatch.setattr(kai, "_verified_company_bounded", fake_verified_company_bounded)
    monkeypatch.setattr(
        kai, "decide",
        lambda company: Decision(call="BUY", weighted_score=0.5, breakdown=[], explanation="test"),
    )

    ranked, diagnostics = kai._rank_candidates()

    assert ranked == [("GOOD_CODE", 0.5)]
    timeout_entries = [d for d in diagnostics if d["code"] == "TIMEOUT_CODE"]
    assert len(timeout_entries) == 1
    assert timeout_entries[0]["status"] == "ERROR"
    assert timeout_entries[0]["retryable"] is True
    assert "timeout" in timeout_entries[0]["reason"]


def test_eligible_buy_reaches_paper_filled_and_live_trading_stays_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_ENFORCE_MARKET_SESSION", "false")
    monkeypatch.setenv("KIASHA_PAPER_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("KIASHA_PAPER_MIN_CONFIDENCE", "0.40")
    # Deliberately flipped "on" to prove the Paper path never reads it.
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    db_path = str(tmp_path / "shared.sqlite3")
    audit = AuditStore(db_path)
    paper = PaperExecutionStore(db_path)
    paper_sell = PaperSellStore(db_path)
    monkeypatch.setattr(kai, "AUDIT", audit)
    monkeypatch.setattr(kai, "PAPER", paper)
    monkeypatch.setattr(kai, "PAPER_SELL", paper_sell)
    monkeypatch.setattr(kai, "STORE", AutoInvestStore(str(tmp_path / "settings.sqlite3")))

    user_id = "test-user"
    kai.STORE.update_settings(user_id=user_id, enabled=True, horizon="short", max_daily_trades=3)

    code = "TESTBUY"
    monkeypatch.setattr(kai, "_candidate_symbols", lambda: [code])
    monkeypatch.setattr(
        kai, "decide",
        lambda company: Decision(call="BUY", weighted_score=0.8, breakdown=[], explanation="test"),
    )
    monkeypatch.setattr(
        kai, "_verified_company_bounded",
        lambda c: ({"market": {"quote_fetched_at": None}}, 1000.0),
    )
    proposal = KiashaAIProposal(
        code=code, horizon="short", action="BUY", confidence=0.9,
        position_pct=5.0, thesis="verified test thesis", risks=[], model="test-model",
    )
    monkeypatch.setattr(kai, "_analyze_with_ai_bounded", lambda code, *, horizon: proposal)

    result = kai.run_user_auto_invest(user_id, force=True)

    assert result["liveExecution"] is False
    assert result["status"] == "COMPLETED"
    filled = [t for t in result["trades"] if t.get("status") == "FILLED"]
    assert len(filled) == 1
    assert filled[0]["receipt"]["status"] == "PAPER_FILLED"
    assert filled[0]["receipt"]["broker"] == "paper"
    assert filled[0]["liveExecution"] is False

    with audit._connect() as conn:
        row = conn.execute("SELECT status, mode FROM order_intents WHERE code=?", (code,)).fetchone()
    assert row is not None
    assert row["status"] == "PAPER_FILLED"
    assert row["mode"] == "paper"
