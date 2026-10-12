import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.issuer import collapse_issuers, issuer_key_of, resolve_issuer_identities
from global_markets.models import InvestorProfile
from global_markets.scan_service import build_coverage_funnel
from tests.test_global_agents import _company, _signals

NOW = datetime(2026, 9, 16, 1, tzinfo=timezone.utc)


def _cand(ticker, name):
    c = _company(ticker=ticker)
    c.name = name
    ev = evidence_agent(c, _signals(), now=NOW)
    return PortfolioCandidate(c, _signals(), ev)


def _profile(**kw):
    base = dict(capital=100_000, base_currency="USD", risk_tolerance="medium", horizon="5y",
                max_position_pct=10, max_country_pct=100, max_sector_pct=100,
                min_cash_reserve_pct=0, max_positions=10)
    base.update(kw)
    return InvestorProfile(**base)


def test_issuer_key_merges_share_classes_not_different_issuers():
    a = issuer_key_of({"name": "Alphabet Inc. Class A Common Stock", "country": "US"})
    c = issuer_key_of({"name": "Alphabet Inc. Class C Capital Stock", "country": "US"})
    t = issuer_key_of({"name": "Tesla, Inc.", "country": "US"})
    assert a == c and a != t


def test_lei_wins_over_name():
    assert issuer_key_of({"lei": "5493006MHB84DD0ZWV18", "name": "x"}) == issuer_key_of(
        {"lei": "5493006mhb84dd0zwv18", "name": "y"})


def test_ranking_collapses_issuer_but_keeps_both_securities():
    rows = [
        {"ticker": "GOOGL", "country": "US", "exchange": "NASDAQ", "score": 0.6, "confidence": 0.8,
         "company": {"name": "Alphabet Inc. Class A", "country": "US", "ticker": "GOOGL"}},
        {"ticker": "GOOG", "country": "US", "exchange": "NASDAQ", "score": 0.5, "confidence": 0.8,
         "company": {"name": "Alphabet Inc. Class C", "country": "US", "ticker": "GOOG"}},
        {"ticker": "TSLA", "country": "US", "exchange": "NASDAQ", "score": 0.4, "confidence": 0.8,
         "company": {"name": "Tesla, Inc.", "country": "US", "ticker": "TSLA"}},
    ]
    out = collapse_issuers(rows, lambda r: r["score"] * r["confidence"])
    assert [r["ticker"] for r in out] == ["GOOGL", "TSLA"]
    assert out[0]["otherSecurities"][0]["ticker"] == "GOOG"


def test_portfolio_caps_issuer_across_share_classes_with_traceable_reason():
    googl, goog = _cand("GOOGL", "Alphabet Inc. Class A"), _cand("GOOG", "Alphabet Inc. Class C")
    result = portfolio_agent(_profile(), [googl, goog])
    total = sum(a.weight_pct for a in result.allocations)
    assert total <= 10.0 + 1e-6  # one issuer, one 10% cap
    rej = [r for r in result.rejections if r["constraint"] == "max_issuer_pct"]
    assert rej and rej[0]["issuer"].startswith("NAME:US:alphabet")
    assert any("max_issuer_pct" in e for e in result.excluded)


def test_every_exclusion_has_a_structured_constraint():
    blocked = _cand("BAD", "Bad Co")
    low = _cand("LOW", "Low Co")
    result = portfolio_agent(_profile(), [low], min_score=0.99)
    assert result.status == "NO_RECOMMENDATION"
    assert result.rejections and result.rejections[0]["constraint"] == "decision_threshold"
    assert len(result.rejections) == len(result.excluded)
    _ = blocked


def test_coverage_funnel_keeps_stages_separate():
    f = build_coverage_funnel([{"eligibleEquities": 3017, "screenedEquities": 2997, "deepAnalyzed": 75,
                                "evidencePass": 40, "qualifiedBuy": 3, "rankingEligible": True}])
    assert f["stages"] == {"markets": 1, "discovered": 3017, "lightweightScreened": 2997, "deepAnalyzed": 75,
                           "evidencePass": 40, "qualifiedBuy": 3}
    assert f["pctOfDiscovered"]["deepAnalyzed"] == 2.49
    assert "must not be read as analysis coverage" in f["warning"]


def test_funnel_never_mixes_eligible_and_excluded_market_populations():
    rows = [
        {"eligibleEquities": 100, "screenedEquities": 98, "deepAnalyzed": 25, "evidencePass": 20, "qualifiedBuy": 2, "rankingEligible": True},
        {"eligibleEquities": 16, "screenedEquities": 16, "deepAnalyzed": 16, "evidencePass": 11, "qualifiedBuy": 1, "rankingEligible": False},
    ]
    f = build_coverage_funnel(rows, qualified_issuers=2)
    assert f["stages"]["discovered"] == 100 and f["stages"]["deepAnalyzed"] == 25 and f["stages"]["qualifiedBuy"] == 2
    assert f["scopes"]["allConnectedMarkets"]["discovered"] == 116
    assert f["scopes"]["allConnectedMarkets"]["qualifiedBuy"] == 3
    assert f["scopes"]["rankingEligibleMarkets"]["qualifiedIssuers"] == 2
    assert f["stagesScope"] == "rankingEligibleMarkets"


def test_asml_dual_listing_collapses_to_one_issuer():
    # Regression: Euronext "ASML Holding N.V." and NASDAQ "New York Registry Shares" were two issuers.
    rows = [
        {"ticker": "ASML", "country": "NL", "exchange": "EURONEXT_AMSTERDAM", "score": 0.7, "confidence": 0.8,
         "company": {"name": "ASML Holding N.V.", "country": "NL", "ticker": "ASML", "exchange": "EURONEXT_AMSTERDAM"}},
        {"ticker": "ASML", "country": "US", "exchange": "NASDAQ", "score": 0.6, "confidence": 0.8,
         "company": {"name": "ASML Holding N.V. - New York Registry Shares", "country": "US", "ticker": "ASML", "exchange": "NASDAQ"}},
        {"ticker": "TSLA", "country": "US", "exchange": "NASDAQ", "score": 0.4, "confidence": 0.8,
         "company": {"name": "Tesla, Inc.", "country": "US", "ticker": "TSLA", "exchange": "NASDAQ"}},
    ]
    out = collapse_issuers(rows, lambda r: r["score"] * r["confidence"])
    assert [r["ticker"] for r in out] == ["ASML", "TSLA"]
    assert out[0]["country"] == "NL"
    assert out[0]["otherSecurities"][0]["exchange"] == "NASDAQ"  # still reachable


def test_depositary_without_unique_home_listing_is_not_merged_by_guess():
    assert issuer_key_of({"name": "Foo Holdings N.V. ADR", "country": "US"}) == "NAME:*:foo"
    keys = resolve_issuer_identities([{"name": "Foo Holdings N.V. ADR", "country": "US"}, {"name": "Bar NV", "country": "NL"}])
    assert keys[0] == "NAME:*:foo"
    assert issuer_key_of({"name": "ASML Holding N.V.", "country": "NL"}) == issuer_key_of({"name": "ASML Holding NV", "country": "NL"})


def test_portfolio_caps_asml_dual_listing_once():
    nl, us = _cand("ASML", "ASML Holding N.V."), _cand("ASML", "ASML Holding N.V. - New York Registry Shares")
    nl.company.country, us.company.country = "NL", "US"
    us.company.exchange = "NASDAQ"
    result = portfolio_agent(_profile(), [nl, us])
    assert sum(a.weight_pct for a in result.allocations) <= 10.0 + 1e-6


def test_real_asml_rows_lei_home_vs_cik_us_collapse():
    # Real cached shapes: NL row has LEI, US row has only SEC CIK 937966 and no LEI/ISIN.
    rows = [
        {"ticker": "ASML", "country": "NL", "exchange": "EURONEXT_AMSTERDAM", "score": 0.32, "confidence": 0.52,
         "company": {"name": "ASML Holding N.V.", "country": "NL", "ticker": "ASML", "lei": "724500Y6DUVHQD6OXN27"}},
        {"ticker": "ASML", "country": "US", "exchange": "NASDAQ", "score": 0.43, "confidence": 0.63,
         "company": {"name": "ASML HOLDING NV", "country": "US", "ticker": "ASML", "raw_provider_fields": {"sec_cik": 937966}}},
    ]
    out = collapse_issuers(rows, lambda r: r["score"] * r["confidence"])
    assert len(out) == 1 and out[0]["country"] == "US" and out[0]["issuerKey"] == "LEI:724500Y6DUVHQD6OXN27"
    assert out[0]["otherSecurities"][0]["exchange"] == "EURONEXT_AMSTERDAM"


def test_name_bridge_for_unlisted_pair_requires_unique_home_and_never_merges_two_homes():
    cik = {"name": "Shell plc", "country": "US", "raw_provider_fields": {"sec_cik": 1306965}}
    home = {"name": "Shell plc", "country": "GB", "lei": "21380068P1DRHMJ8KU70"}
    assert resolve_issuer_identities([cik, home]) == ["LEI:21380068P1DRHMJ8KU70"] * 2
    other_home = {"name": "Shell plc", "country": "NL", "lei": "5493001KJTIIGC8Y1R12"}
    keys = resolve_issuer_identities([cik, home, other_home])
    assert keys[0] == "CIK:1306965"  # ambiguous: two distinct home entities, not merged by guess
    assert resolve_issuer_identities([{"name": "Tesla, Inc.", "country": "US", "raw_provider_fields": {"sec_cik": 1318605}}]) == ["CIK:1318605"]
