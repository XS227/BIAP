import json
from datetime import datetime, timezone

import pytest

from global_markets import benchmark_refresh as br
from global_markets.source_cache import write_json_atomic


def _rows(n):
    return [{"ticker": f"T{i}", "company": {"ticker": f"T{i}", "sector": "Tech", "pe": 15.0}} for i in range(n)]


def _payload(n=120, **over):
    return {"rankingEligible": True, "screeningCoveragePct": 99.0, "deepResults": _rows(n), **over}


def _seed(tmp_path, monkeypatch, n=100):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    path = tmp_path / "scan-cache" / "DE" / "XETRA.json"
    write_json_atomic(path, {"schemaVersion": 3, "cachedAt": "2026-10-14T08:00:00+00:00", "country": "DE",
                             "exchange": "XETRA", "payload": _payload(n)})
    return path


NOW = datetime(2026, 10, 16, 6, tzinfo=timezone.utc)


def test_valid_refresh_replaces_cache_and_keeps_one_previous_generation(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    out = br.refresh_benchmark("DE", "XETRA", scan=lambda **k: _payload(130), now=NOW)
    assert out["status"] == "OK" and out["replaced"] and out["deepRows"] == 130
    wrapper = json.loads(path.read_text())
    assert wrapper["cachedAt"].startswith("2026-10-16T06") and wrapper["schemaVersion"] == 3
    assert json.loads(path.with_name("XETRA.json.prev").read_text())["cachedAt"].startswith("2026-10-14")


@pytest.mark.parametrize("bad", [
    _payload(10),                                    # too few rows
    _payload(20, rankingEligible=False),
    _payload(120, screeningCoveragePct=40.0),
    _payload(120, deepResults="nope"),
])
def test_invalid_payload_never_replaces_the_cache(tmp_path, monkeypatch, bad):
    path = _seed(tmp_path, monkeypatch)
    before = path.read_bytes()
    out = br.refresh_benchmark("DE", "XETRA", scan=lambda **k: bad, now=NOW)
    assert out["status"] == "REJECTED" and not out["replaced"] and out["problems"]
    assert path.read_bytes() == before


def test_provider_failure_keeps_previous_cache(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    before = path.read_bytes()

    def boom(**k):
        raise TimeoutError("provider down")

    out = br.refresh_benchmark("DE", "XETRA", scan=boom, now=NOW)
    assert out["status"] == "ERROR" and "TimeoutError" in out["error"] and not out["replaced"]
    assert path.read_bytes() == before


def test_large_shrink_is_rejected(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, n=150)
    before = path.read_bytes()
    out = br.refresh_benchmark("DE", "XETRA", scan=lambda **k: _payload(60), now=NOW)
    assert out["status"] == "REJECTED" and path.read_bytes() == before


def test_failed_refresh_leaves_decisions_failing_closed(tmp_path, monkeypatch):
    """Cache older than 24 h + failed refresh => no benchmark => a BUY cannot be accepted."""
    from global_markets.service import _scan_peer_state
    from tests.test_global_governance_agent import _company

    path = _seed(tmp_path, monkeypatch)
    br.refresh_benchmark("DE", "XETRA", scan=lambda **k: (_ for _ in ()).throw(OSError("x")), now=NOW)
    state = _scan_peer_state(_company(country="DE", exchange="XETRA"))[1]
    assert state == "scan_cache_stale"


def test_lock_blocks_second_refresh_and_is_released(tmp_path):
    p = tmp_path / "XETRA.json"
    with br.refresh_lock(p):
        with pytest.raises(br.RefreshLocked):
            with br.refresh_lock(p):
                pass
    with br.refresh_lock(p):
        pass


def test_cleanup_removes_only_old_own_temp_files(tmp_path):
    import os, time
    p = tmp_path / "XETRA.json"
    p.write_text("{}")
    (tmp_path / "XETRA.json.prev").write_text("{}")
    old, new = tmp_path / "XETRA.json.a.tmp", tmp_path / "XETRA.json.b.tmp"
    other = tmp_path / "FRANKFURT.json.c.tmp"
    for f in (old, new, other):
        f.write_text("x")
    os.utime(old, (time.time() - 7200,) * 2)
    os.utime(other, (time.time() - 7200,) * 2)
    assert br.cleanup_stale_temp(p) == 1
    assert not old.exists() and new.exists() and other.exists() and p.exists()
    assert (tmp_path / "XETRA.json.prev").exists()
