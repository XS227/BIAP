from global_markets.scanner import GlobalMarketScanner


def test_readiness_blocks_non_authoritative_universe():
    scanner=GlobalMarketScanner()
    result=scanner._readiness(
        country="IT", exchange="EURONEXT_MILAN", universe_count=200, screened_count=200,
        deep_results=[], live_market_data=True, market_source="test", partial_universe=False,
        screening_errors=[], universe_authoritative=False, universe_source="twelve-data-universe-demo",
    )
    assert result["rankingEligible"] is False
    assert "authoritative_universe_unavailable" in result["reasons"]
    assert result["universeAuthoritative"] is False


def test_eodhd_can_be_full_market_source_without_twelve_key(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    monkeypatch.setenv("BIAP_EODHD_API_TOKEN", "token")
    scanner=GlobalMarketScanner()
    assert scanner.eodhd_bulk is not None
