from __future__ import annotations

import market_scanner


def test_bulk_candidate_scores_verified_market_row():
    row = {
        "insCode": "123",
        "lVal18AFC": "نماد",
        "lVal30": "شرکت نمونه",
        "flow": 1,
        "pDrCotVal": 1050,
        "pClosing": 1040,
        "priceYesterday": 1000,
        "qTotTran5J": 2_000_000,
        "qTotCap": 5_000_000_000,
        "zTotTran": 1200,
    }
    candidate = market_scanner._bulk_candidate(row)
    assert candidate is not None
    assert candidate.code == "123"
    assert candidate.symbol == "نماد"
    assert candidate.change_percent == 5.0
    assert candidate.discovery_score > 0


def test_bulk_candidate_rejects_non_market_flow():
    assert market_scanner._bulk_candidate({
        "insCode": "123", "lVal18AFC": "X", "flow": 9, "pClosing": 100,
    }) is None


def test_deep_analyze_timeout_skips_candidate_without_hanging(monkeypatch, tmp_path):
    """A stuck deep-analysis candidate must be skipped, not hang the whole scan.

    Regression test for a bug where deep analysis ran on a ThreadPoolExecutor
    and checked `job.result(timeout=...)` inside `for job in as_completed(...)`:
    as_completed() only yields a future once it is already done, so that
    per-job timeout could never actually fire, and the non-daemon executor
    threads could block process exit on top of that. This asserts the fix
    (run_with_deadline per candidate) still lets one DeadlineExceeded skip
    that candidate while the rest of the scan completes.
    """
    monkeypatch.setenv("BIAP_MARKET_SCAN_CACHE", str(tmp_path / "scan.json"))
    rows = [
        {"insCode": "1", "lVal18AFC": "STUCK", "flow": 1, "pDrCotVal": 100,
         "priceYesterday": 100, "qTotTran5J": 10, "qTotCap": 10, "zTotTran": 10},
        {"insCode": "2", "lVal18AFC": "OK", "flow": 1, "pDrCotVal": 200,
         "priceYesterday": 200, "qTotTran5J": 10, "qTotCap": 10, "zTotTran": 10},
    ]
    monkeypatch.setattr(market_scanner, "_read_market_watch", lambda timeout: rows)

    def fake_run_with_deadline(fn, item, delay, *, timeout):
        if item.code == "1":
            raise market_scanner.DeadlineExceeded("candidate stuck past deadline")
        return {
            "code": item.code, "symbol": item.symbol, "name": item.name,
            "discoveryScore": item.discovery_score, "kiashaCall": "BUY", "kiashaScore": 1.0,
            "explanation": "", "agentBreakdown": {}, "changePercent": 0.0,
            "tradeValue": 0.0, "volume": 0.0, "dataAvailability": {}, "dataDiagnostics": {},
        }

    monkeypatch.setattr(market_scanner, "run_with_deadline", fake_run_with_deadline)

    payload = market_scanner.refresh_market_scan(force=True)

    assert payload["deepErrors"] == [{"code": "1", "symbol": "STUCK", "reason": "timeout after 45.0s"}]
    assert [item["code"] for item in payload["top10"]] == ["2"]


def test_degraded_scan_never_invents_top10(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_MARKET_SCAN_CACHE", str(tmp_path / "scan.json"))
    monkeypatch.setattr(market_scanner, "_read_market_watch", lambda timeout: [])
    monkeypatch.setattr(market_scanner, "get_symbol_universe", lambda timeout: [object(), object()])

    payload = market_scanner.refresh_market_scan(force=True)
    assert payload["status"] == "DEGRADED"
    assert payload["universeCount"] == 2
    assert payload["marketRowsScanned"] == 0
    assert payload["top10"] == []
