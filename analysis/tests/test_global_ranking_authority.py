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


def _unreleased(**kw):
    return GlobalMarketScanner()._readiness(
        country="DE", exchange="XETRA", universe_count=100, screened_count=100,
        deep_results=[{"ticker": "A", "evidence": {"status": "PASS"}}], live_market_data=True, market_source="test",
        partial_universe=False, screening_errors=["batch 1: no key"], universe_authoritative=True,
        universe_source="test", **kw)


def test_investment_mode_releases_tiers_while_conservative_ranking_stays_blocked(monkeypatch):
    monkeypatch.setenv("DECISION_MODE", "investment")
    monkeypatch.setenv("BIAP_INVESTMENT_SCOPE", "all")
    result = _unreleased()
    assert result["rankingEligible"] is False and "market_data_batch_errors" in result["reasons"]
    assert result["tiersReleased"] is True and "market_data_batch_errors" in result["releaseFlags"]


def test_conservative_mode_does_not_release_tiers(monkeypatch):
    monkeypatch.delenv("DECISION_MODE", raising=False)
    result = _unreleased()
    assert result["tiersReleased"] is False and result["releaseFlags"] == []


def test_advisory_gates_are_marked_only_when_requested():
    gates = {"universe": 10, "analyzed": 10, "evidencePass": 8, "scoredAndComplete": 8, "buyCandidates": 1,
             "rankingEligible": 3, "rankMinCoveragePct": 60, "callsAmongScored": {}}
    plain = GlobalMarketScanner.ranking_gates(gates, buy_after_issuer=1, ranking_eligible=False, readiness_reasons=["x"])
    adv = GlobalMarketScanner.ranking_gates(gates, buy_after_issuer=1, ranking_eligible=False, readiness_reasons=["x"], advisory=True)
    assert not any("advisory" in g for g in plain)
    assert {g["gate"] for g in adv if g.get("advisory")} == {"market_ranking_released", "ranking_evidence_standard", "buy_threshold"}
