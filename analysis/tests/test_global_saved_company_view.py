"""Offline tests: saved-company preview never writes or runs a fresh analysis."""
import json
import sqlite3
import zlib

from global_markets.saved_company_view import saved_company_view


def _ledger(path, payload, *, ticker="ABC", financial=None):
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE ledger (ticker TEXT, in_universe INTEGER, result BLOB, "
            "status TEXT, reason TEXT, source TEXT, analyzed_at TEXT, financial TEXT)"
        )
        db.execute(
            "INSERT INTO ledger VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
            (ticker, zlib.compress(json.dumps(payload).encode("utf-8")),
             "COMPLETE", "stored", "SAVED_LEDGER", "2026-10-30T12:00:00+00:00",
             json.dumps(financial or {"coreComplete": True, "coveragePct": 80})),
        )


def test_saved_projection_is_narrow_and_read_only(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    payload = {
        "ticker": "ABC", "name": "Sample Issuer", "currency": "USD",
        "company": {
            "revenue": 1200, "net_income": -5, "total_assets": 400,
            "total_liabilities": 150, "raw_provider_fields": {"secret": "DO_NOT_EXPOSE"},
        },
        "evidence": {"status": "WARN", "coverage": 0.8},
        "fundamentalEvidence": {"sourceProvider": "OFFICIAL", "reportPeriod": "FY2025"},
        "signals": [{"agent": "fundamental", "vote": 0.2, "confidence": 0.7,
                     "reasoning": "Stored evidence"}],
        "decisionTable": {"kiasha": {"call": "HOLD", "confidence": 0.5}},
        "providerDiagnostics": {"credential": "DO_NOT_EXPOSE"},
    }
    _ledger(path, payload)
    before = path.read_bytes()
    view = saved_company_view("US", "NASDAQ", "ABC", path=path)
    assert view["mode"] == "SAVED_READ_ONLY"
    assert view["proxyCalled"] is False
    assert view["eligibleForInvestmentDecision"] is False
    assert view["financials"]["net_income"] == -5
    assert view["agents"][0]["name"] == "fundamental"
    assert view["kiasha"]["call"] == "HOLD"
    assert view["evidence"]["sourceProvider"] == "OFFICIAL"
    assert "DO_NOT_EXPOSE" not in json.dumps(view)
    assert path.read_bytes() == before
    assert saved_company_view("US", "NASDAQ", "UNKNOWN", path=path) is None


def test_unavailable_or_corrupt_saved_result_fails_closed(tmp_path):
    path = tmp_path / "missing.sqlite3"
    assert saved_company_view("US", "NASDAQ", "ABC", path=path) is None
    _ledger(path, {"ticker": "ABC", "company": {"revenue": float("nan")}})
    view = saved_company_view("US", "NASDAQ", "ABC", path=path)
    assert view["financials"]["revenue"] is None
    with sqlite3.connect(path) as db:
        db.execute("UPDATE ledger SET result=?", (b"not-zlib",))
    assert saved_company_view("US", "NASDAQ", "ABC", path=path) is None
