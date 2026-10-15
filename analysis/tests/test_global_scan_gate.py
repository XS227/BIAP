import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from global_markets.providers import GlobalProviderError
from global_markets.scan_gate import ScanFailure, ScanGate, classify_failure


def test_single_flight_shares_one_run():
    gate = ScanGate(max_concurrent=2, queue_wait_sec=5)
    calls = []
    release = threading.Event()

    def slow():
        calls.append(1)
        release.wait(5)
        return {"status": "COMPLETE_SCAN"}

    out = []
    threads = [threading.Thread(target=lambda: out.append(gate.run(("GB", "LSE"), slow))) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    release.set()
    for t in threads:
        t.join(5)
    assert len(calls) == 1
    assert len(out) == 3 and sum(1 for _r, info in out if info["sharedInFlight"]) == 2


def test_busy_gate_returns_retryable_failure_not_empty_result():
    gate = ScanGate(max_concurrent=1, queue_wait_sec=1)
    release = threading.Event()
    t = threading.Thread(target=lambda: gate.run("a", lambda: release.wait(5) or {}))
    t.start()
    time.sleep(0.2)
    with pytest.raises(ScanFailure) as err:
        gate.run("b", lambda: {"ok": True})
    release.set()
    t.join(5)
    assert err.value.code == "SCAN_BUSY" and err.value.retryable and err.value.retry_after_sec


def test_failures_are_classified_and_propagate_to_followers():
    assert classify_failure(httpx.ReadTimeout("x")).code == "UPSTREAM_TIMEOUT"
    assert classify_failure(httpx.ConnectError("x")).code == "UPSTREAM_NETWORK_ERROR"
    assert classify_failure(GlobalProviderError("batch quote failed")).code == "PROVIDER_UNAVAILABLE"
    internal = classify_failure(RuntimeError("boom"))
    assert internal.code == "SCAN_INTERNAL_ERROR" and not internal.retryable and internal.http_status == 500

    gate = ScanGate()
    with pytest.raises(ScanFailure):
        gate.run("k", lambda: (_ for _ in ()).throw(httpx.ReadTimeout("t")))
    # gate recovers after a failure
    assert gate.run("k", lambda: {"ok": 1})[0] == {"ok": 1}


def test_scan_route_returns_structured_error_never_empty_success(monkeypatch):
    import global_routes
    from global_api_server import app

    def boom(**_kw):
        raise httpx.ConnectError("Software caused connection abort")

    monkeypatch.setattr(global_routes, "scan_global_market", boom)
    client = TestClient(app)
    r = client.post("/global/scan", json={"country": "GB", "exchange": "LSE"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "UPSTREAM_NETWORK_ERROR" and detail["retryable"] is True
    assert detail["country"] == "GB" and detail["exchange"] == "LSE"
    assert r.headers.get("retry-after")


def test_scan_route_gzips_large_payload(monkeypatch):
    import global_routes
    from global_api_server import app

    monkeypatch.setattr(
        global_routes, "scan_global_market",
        lambda **_kw: {"status": "COMPLETE_SCAN", "deepResults": [{"ticker": "X" * 50}] * 2000},
    )
    r = TestClient(app).post(
        "/global/scan", json={"country": "GB", "exchange": "LSE"}, headers={"Accept-Encoding": "gzip"}
    )
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
