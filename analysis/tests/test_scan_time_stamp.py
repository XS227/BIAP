"""P3 (v2): every score row carries the time of the scan that produced it; v1 payloads stay byte-identical."""
import pytest

from global_markets import analysis_ledger as al
from tests.test_global_analysis_ledger import _register, _drain, _result  # noqa: F401  (fixture helpers)


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    yield led
    led.close()


def test_ledger_summaries_carry_analyzed_at_only_in_v2(ledger, monkeypatch):
    universe = _register(ledger, 3)
    _drain(ledger, universe, lambda c: _result(c.ticker))
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert all(r.get("analyzedAt") for r in ledger.summaries(limit=10))
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    assert all("analyzedAt" not in r for r in ledger.summaries(limit=10))


def test_detail_headline_comes_from_snapshot_and_live_is_kept_apart(ledger, monkeypatch):
    from global_routes import _official_snapshot_view
    universe = _register(ledger, 1)
    _drain(ledger, universe, lambda c: _result(c.ticker))
    live = {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "T000", "score": 0.99, "confidence": 0.1,
            "call": "HOLD_OR_WATCH", "analyzedAt": "2030-01-01T00:00:00+00:00"}
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    assert _official_snapshot_view(live) == live
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    out = _official_snapshot_view(live)
    assert out["score"] == 0.5 and out["confidence"] == 0.6 and out["officialSnapshot"] is True
    assert out["analyzedAt"] != live["analyzedAt"]
    assert out["live"]["score"] == 0.99 and out["live"]["analyzedAt"] == live["analyzedAt"]
    assert _official_snapshot_view({**live, "ticker": "NOPE"}) == {**live, "ticker": "NOPE"}
