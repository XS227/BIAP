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
