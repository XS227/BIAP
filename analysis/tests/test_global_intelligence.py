"""Regression coverage for the read-only intelligence preview.

No external market requests and no production files are needed.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import global_intelligence_routes as routes
from global_markets.intelligence import build_company_dashboard, answer_company_question


def _analysis():
    return {
        "country": "US",
        "exchange": "NASDAQ",
        "mic": "XNAS",
        "ticker": "TEST",
        "name": "Fixture Corp",
        "currency": "USD",
        "call": "NO_RECOMMENDATION",
        "score": 0.45,
        "confidence": 0.67,
        "evidence": {"status": "WARN", "missing_critical": ["fresh_price"], "contradictions": []},
        "distress": {"status": "UNKNOWN", "positive_block": False},
        "signals": [{"agent": "fundamental", "vote": 0.3, "confidence": 0.7, "reasoning": "fixture"}],
        "fundamentalEvidence": {
            "values": {
                "revenue": 120000000,
                "revenue_prev": 100000000,
                "revenue_yoy_pct": 20,
                "net_income": 10000000,
                "net_margin_pct": 8.3,
                "total_debt": None,
                "total_equity": 110000000,
                "operating_cash_flow": 9000000,
            },
            "officialStatus": "OFFICIAL_CURRENT",
            "reportPeriod": "2025-12-31",
            "filingDate": "2026-03-14",
            "sourceUrl": "https://example.org/filing",
            "sourceProvider": "fixture",
            "isOfficial": True,
            "freshnessTier": "LAST_ANNUAL_FILING",
            "limitations": ["interim results not available"],
        },
        "company": {
            "currency": "USD",
            "reporting_currency": "USD",
            "price": 45.0,
            "price_observed_at": "2026-10-26T18:00:00+00:00",
            "market_cap": 1500000000,
            "sources": [
                {"provider": "fixture", "source_type": "official_regulatory_xbrl",
                 "source_url": "https://example.org/filing", "period_end": "2025-12-31"}
            ],
        },
    }


def test_dashboard_retains_unchanged_decision_and_traceable_periods():
    original = _analysis()
    dashboard = build_company_dashboard(original)
    values = {row["key"]: row for row in dashboard["metrics"]}
    assert dashboard["decision"]["existingCall"] == "NO_RECOMMENDATION"
    assert original["call"] == "NO_RECOMMENDATION"
    assert dashboard["evidence"]["status"] == "WARN"
    assert dashboard["evidence"]["reportPeriod"] == "2025-12-31"
    assert values["revenue"]["value"] == 120000000
    assert values["revenue"]["asOf"] == "2025-12-31"
    assert values["price"]["asOf"] == "2026-10-26T18:00:00+00:00"
    assert values["revenue"]["fieldVerified"] is False
    assert dashboard["sources"][0]["sourceUrl"] == "https://example.org/filing"


def test_grounded_persian_answer_reports_missing_debt_instead_of_guessing():
    dashboard = build_company_dashboard(_analysis())
    answer = answer_company_question(dashboard, "بدهی شرکت چقدر است؟", "fa")
    assert answer["supported"]
    assert "داده موجود نیست" in answer["answer"]
    assert "2025-12-31" in answer["answer"]
    assert answer["generativeModelUsed"] is False


def test_unknown_question_does_not_make_up_response():
    out = answer_company_question(build_company_dashboard(_analysis()), "آینده ده ساله این شرکت؟")
    assert out["supported"] is False
    assert out["matchedTopics"] == []


def test_nonfinite_and_boolean_metrics_are_unavailable():
    x = _analysis()
    x["company"]["price"] = float("nan")
    x["fundamentalEvidence"]["values"]["revenue"] = True
    values = {row["key"]: row for row in build_company_dashboard(x)["metrics"]}
    assert values["price"]["available"] is False
    assert values["revenue"]["available"] is False


def test_analyst_routes_are_read_only_and_validate_inputs(monkeypatch):
    monkeypatch.setattr(routes, "_analysis", lambda _instrument: _analysis())
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    instrument = {"country": "US", "exchange": "NASDAQ", "ticker": "TEST"}
    dashboard = client.post("/global/intelligence/dashboard", json=instrument)
    assert dashboard.status_code == 200
    assert dashboard.json()["decision"]["unchanged"] is True
    answer = client.post("/global/intelligence/ask", json={
        "instrument": instrument, "question": "What is the revenue?", "language": "en",
    })
    assert answer.status_code == 200
    assert "120,000,000" in answer.json()["answer"]
    invalid = client.post("/global/intelligence/ask", json={
        "instrument": instrument, "question": "hi", "language": "en",
    })
    assert invalid.status_code == 422


def test_analyze_membership_errors_are_not_swallowed(monkeypatch):
    def bad_seed(_instrument):
        raise HTTPException(status_code=400, detail="not listed")
    monkeypatch.setattr(routes, "_seed", bad_seed)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    response = client.post("/global/intelligence/dashboard", json={
        "country": "US", "exchange": "NASDAQ", "ticker": "UNKNOWN",
    })
    assert response.status_code == 400
