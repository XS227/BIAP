import global_markets.scan_service as scan_service
from global_markets.runtime import build_registry
from global_markets.scan_service import _global_scan_status, _global_top_markets


def test_global_top_markets_cover_every_enabled_non_iran_exchange_without_keys(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    monkeypatch.delenv("BIAP_OPENDART_API_KEY", raising=False)
    markets = _global_top_markets()
    assert ("BR", "B3") in markets
    assert ("JP", "TSE_JP") in markets
    assert ("KR", "KRX") in markets
    assert ("CA", "TSXV") in markets
    assert ("AE", "ADX") in markets
    assert ("IN", "BSE") in markets
    assert not any(country == "IR" for country, _ in markets)
    assert len(markets) == 35


def test_global_top_markets_can_limit_operational_ranking_scope(monkeypatch):
    monkeypatch.setenv(
        "BIAP_GLOBAL_RANKING_MARKETS",
        "US:NASDAQ,FR:EURONEXT_PARIS,XX:NOT_REAL,bad-value",
    )
    assert _global_top_markets() == (
        ("US", "NASDAQ"),
        ("FR", "EURONEXT_PARIS"),
    )


def test_bounded_scan_cannot_downgrade_complete_market_cache(monkeypatch, tmp_path):
    path = tmp_path / "NASDAQ.json"
    monkeypatch.setattr(scan_service, "_scan_cache_path", lambda *_: path)
    scan_service._write_scan_cache(
        "US", "NASDAQ", {"rankingEligible": True, "recommendations": [{"ticker": "MSFT"}]}
    )
    scan_service._write_scan_cache(
        "US", "NASDAQ", {"rankingEligible": False, "recommendations": []}
    )
    cached = scan_service.read_json(path, default={})["payload"]
    assert cached["rankingEligible"] is True
    assert cached["recommendations"][0]["ticker"] == "MSFT"


def test_global_top_market_scope_does_not_change_when_regulator_keys_are_added(monkeypatch):
    monkeypatch.setenv("BIAP_EDINET_API_KEY", "configured")
    monkeypatch.setenv("BIAP_OPENDART_API_KEY", "configured")
    markets = _global_top_markets()
    assert ("JP", "TSE_JP") in markets
    assert ("KR", "KRX") in markets
    assert len(markets) == 35


def test_every_global_scan_market_has_all_three_provider_layers(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    monkeypatch.delenv("BIAP_OPENDART_API_KEY", raising=False)
    registry = build_registry()

    for country, exchange in _global_top_markets():
        assert registry.universe(country, exchange) is not None
        assert registry.market(country, exchange) is not None
        assert registry.fundamentals(country, exchange) is not None


def test_global_status_never_calls_partial_zero_result_global_no_recommendation():
    assert _global_scan_status(
        eligible_markets=11, total_markets=18, recommendation_count=0
    ) == "PARTIAL_GLOBAL_NO_RECOMMENDATION"


def test_global_status_marks_partial_scope_when_candidates_exist():
    assert _global_scan_status(
        eligible_markets=11, total_markets=18, recommendation_count=3
    ) == "PARTIAL_GLOBAL_SCAN"


def test_global_status_uses_full_scope_labels_only_when_all_markets_ready():
    assert _global_scan_status(
        eligible_markets=18, total_markets=18, recommendation_count=0
    ) == "NO_RECOMMENDATION"
    assert _global_scan_status(
        eligible_markets=18, total_markets=18, recommendation_count=2
    ) == "GLOBAL_TOP10"



def test_global_top_cache_miss_never_runs_full_market_scan_in_user_request(monkeypatch):
    monkeypatch.setattr(
        scan_service,
        "_global_top_markets",
        lambda: (("FR", "EURONEXT_PARIS"), ("BR", "B3")),
    )
    cached_fr={
        "status":"NO_RECOMMENDATION",
        "country":"FR",
        "exchange":"EURONEXT_PARIS",
        "rankingEligible":True,
        "universeDiscovered":100,
        "universeScreened":98,
        "deepAnalyzed":10,
        "screeningCoveragePct":98.0,
        "fundamentalCoveragePct":100.0,
        "recommendations":[],
    }
    monkeypatch.setattr(
        scan_service,
        "_read_scan_cache",
        lambda country, exchange, max_age_hours: cached_fr if country=="FR" else None,
    )

    def forbidden_live_scan(**kwargs):
        raise AssertionError("Global Top user request must never start a full-market scan")

    monkeypatch.setattr(scan_service,"scan_global_market",forbidden_live_scan)
    result=scan_service.scan_global_top10(top_n=10,max_age_hours=30)

    assert result["marketsScanned"]==2
    assert result["marketsEligible"]==1
    assert result["marketsExcluded"]==1
    missing=next(row for row in result["markets"] if row["country"]=="BR")
    assert missing["status"]=="SCAN_CACHE_MISSING"
    assert missing["rankingEligible"] is False
