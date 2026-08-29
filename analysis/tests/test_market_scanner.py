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


def test_degraded_scan_never_invents_top10(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_MARKET_SCAN_CACHE", str(tmp_path / "scan.json"))
    monkeypatch.setattr(market_scanner, "_read_market_watch", lambda timeout: [])
    monkeypatch.setattr(market_scanner, "get_symbol_universe", lambda timeout: [object(), object()])

    payload = market_scanner.refresh_market_scan(force=True)
    assert payload["status"] == "DEGRADED"
    assert payload["universeCount"] == 2
    assert payload["marketRowsScanned"] == 0
    assert payload["top10"] == []
