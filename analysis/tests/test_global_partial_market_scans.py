from datetime import datetime, timezone

import global_markets.scan_service as ss


def _eligible(country, exchange, rows):
    return {
        "status": "COMPLETE_SCAN", "country": country, "exchange": exchange, "rankingEligible": True,
        "universeDiscovered": 100, "universeScreened": 98, "screeningCoveragePct": 98.0,
        "deepResults": rows, "recommendations": rows,
    }


def _buy(ticker, country, exchange):
    return {"ticker": ticker, "country": country, "exchange": exchange, "call": "BUY_CANDIDATE",
            "score": 0.8, "confidence": 0.8, "evidence": {"status": "PASS"}, "company": {"name": ticker}}


def test_missing_market_is_reported_unavailable_and_scan_is_partial(monkeypatch):
    monkeypatch.setattr(ss, "_global_top_markets", lambda: (("US", "NASDAQ"), ("GB", "LSE")))
    now = datetime.now(timezone.utc).isoformat()

    def fake_cache(country, exchange, *, max_age_hours):
        if (country, exchange) == ("US", "NASDAQ"):
            return {**_eligible("US", "NASDAQ", [_buy("MSFT", "US", "NASDAQ")]), "scanCache": {"hit": True, "cachedAt": now, "ageHours": 1}}
        return None  # GB cache missing/stale

    monkeypatch.setattr(ss, "_read_scan_cache", fake_cache)
    out = ss.scan_global_top10(top_n=10)
    assert out["status"] == "PARTIAL_GLOBAL_SCAN"
    assert out["marketsScanned"] == 2 and out["marketsEligible"] == 1 and out["marketsExcluded"] == 1
    gb = next(m for m in out["markets"] if m["country"] == "GB")
    assert gb["status"] == "SCAN_CACHE_MISSING" and gb["rankingEligible"] is False and gb["error"]
    assert gb["recommendationCount"] == 0
    # coverage figures describe only the eligible market, not an invented global total
    assert out["eligibleEquities"] == 100 and out["screenedEquities"] == 98
    assert out["coverageFunnel"]["scopes"]["rankingEligibleMarkets"]["markets"] == 1


def test_no_eligible_market_is_never_reported_as_complete(monkeypatch):
    monkeypatch.setattr(ss, "_global_top_markets", lambda: (("GB", "LSE"),))
    monkeypatch.setattr(ss, "_read_scan_cache", lambda *a, **k: None)
    out = ss.scan_global_top10(top_n=10)
    assert out["status"] == "GLOBAL_DATA_INCOMPLETE" and out["recommendations"] == []


def test_issuer_dual_listing_counts_once(monkeypatch):
    monkeypatch.setattr(ss, "_global_top_markets", lambda: (("US", "NASDAQ"),))
    rows = [_buy("GOOG", "US", "NASDAQ"), _buy("GOOGL", "US", "NASDAQ")]
    for r in rows:
        r["company"] = {"name": "Alphabet Inc.", "lei": "5493006MHB84DD0ZWV18", "isin": "US02079K1079"}
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(ss, "_read_scan_cache", lambda *a, **k: {**_eligible("US", "NASDAQ", rows), "scanCache": {"hit": True, "cachedAt": now}})
    out = ss.scan_global_top10(top_n=10)
    assert out["coverageFunnel"]["scopes"]["rankingEligibleMarkets"]["qualifiedBuy"] == 2
    assert out["qualifiedIssuers"] == 1 and out["recommendationCount"] == 1
