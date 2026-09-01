from agents import AgentVote
import kiasha


def _votes():
    return [
        AgentVote("fundamental", 0.8, 0.9, "fundamental positive"),
        AgentVote("risk", 0.4, 0.8, "risk acceptable"),
        AgentVote("forecast", 0.9, 0.9, "history forecast"),
        AgentVote("comparison", 0.3, 0.7, "peer comparison"),
        AgentVote("technical", 1.0, 1.0, "technical positive"),
        AgentVote("flow", 1.0, 1.0, "flow positive"),
    ]


def _patch_runtime(monkeypatch, scenario):
    monkeypatch.setattr(kiasha, "run_team", lambda _company: _votes())
    monkeypatch.setattr(
        kiasha,
        "_track_record_for_agent",
        lambda agent: (kiasha.TRACK_RECORDS[agent], "untrained-prior", 0),
    )
    monkeypatch.setattr(kiasha, "_scenario_signal", lambda _company: scenario)
    monkeypatch.setattr(kiasha, "_record_observation", lambda _company, _decision: None)


def test_history_free_ipo_suppresses_history_agents_and_blocks_buy(monkeypatch):
    scenario = ({"status": "ok", "confidence": 0.42, "historyObservations": 0, "scenarios": {"base": {"score": 0.0}}}, 0.0, 0.105)
    _patch_runtime(monkeypatch, scenario)
    company = {
        "ticker": "IPO1",
        "name_fa": "نمونه عرضه اولیه",
        "codal_metadata": {"latest_filings": [{"title": "گزارش ارزش گذاری سهام جهت عرضه اولیه"}]},
        "codal": {"revenue_yoy_pct": None, "net_margin_pct": None, "net_profit_current": None},
        "market": {"price": 3185, "pe": None, "market_cap": None, "eps_value": None},
    }

    decision = kiasha.decide(company)

    assert decision.analysis_mode == "ipo"
    assert decision.call == "HOLD"
    assert decision.ipo_review["status"] == "insufficient"
    by_agent = {row["agent"]: row for row in decision.breakdown}
    for agent in ("technical", "flow", "forecast"):
        assert by_agent[agent]["excluded_for_ipo"] is True
        assert by_agent[agent]["weight_pre_norm"] == 0.0
        assert by_agent[agent]["weight_normalized"] == 0.0
    assert by_agent["scenario"]["weight_pre_norm"] == 0.0
    assert by_agent["ipo"]["maturity"] == "insufficient"


def test_history_free_ipo_can_use_verified_fundamentals(monkeypatch):
    scenario = ({"status": "ok", "confidence": 0.42, "historyObservations": 0, "scenarios": {"base": {"score": 0.0}}}, 0.0, 0.105)
    _patch_runtime(monkeypatch, scenario)
    company = {
        "ticker": "IPO2",
        "name_fa": "شرکت جدید",
        "codal_metadata": {"latest_filings": [{"title": "اطلاعیه عرضه اولیه سهام"}]},
        "codal": {
            "revenue_yoy_pct": 22.0,
            "net_margin_pct": 14.0,
            "net_profit_current": 1_000_000,
            "total_assets_current": 5_000_000,
            "total_liabilities_current": 2_000_000,
        },
        "market": {"price": 5000, "pe": 7.5, "market_cap": None, "eps_value": None},
    }

    decision = kiasha.decide(company)

    assert decision.analysis_mode == "ipo"
    assert decision.ipo_review["status"] == "ready"
    by_agent = {row["agent"]: row for row in decision.breakdown}
    assert by_agent["technical"]["weight_pre_norm"] == 0.0
    assert by_agent["fundamental"]["weight_pre_norm"] > 0.0


def test_missing_history_alone_does_not_misclassify_normal_stock_as_ipo(monkeypatch):
    scenario = ({"status": "ok", "confidence": 0.42, "historyObservations": 0, "scenarios": {"base": {"score": 0.0}}}, 0.0, 0.105)
    _patch_runtime(monkeypatch, scenario)
    company = {
        "ticker": "OLD1",
        "name_fa": "شرکت عادی",
        "codal_metadata": {"latest_filings": [{"title": "صورت های مالی دوره ۱۲ ماهه"}]},
        "codal": {"revenue_yoy_pct": 5.0, "net_margin_pct": 8.0, "net_profit_current": 100},
        "market": {"price": 1000},
    }

    decision = kiasha.decide(company)

    assert decision.analysis_mode == "standard"
    assert decision.ipo_review is None
    by_agent = {row["agent"]: row for row in decision.breakdown}
    assert by_agent["technical"]["excluded_for_ipo"] is False
    assert by_agent["technical"]["weight_pre_norm"] > 0.0
