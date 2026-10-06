"""Regression tests for the global official-fundamentals evidence pipeline.

Covers the production failure where every SE/NO issuer returned
``missing=fundamental_source`` although its official FY2025 ESEF report was
lodged with the national OAM, and the related cache/merge/serialization
guarantees. Network is never used.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient

from global_markets import esef
from global_markets.agents import evidence_agent
from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.evidence_contract import (
    STATUS_OFFICIAL_CURRENT,
    STATUS_OFFICIAL_SOURCE_UNAVAILABLE,
    STATUS_OFFICIAL_STALE,
    fundamental_evidence_contract,
    is_official_fundamental_source,
)
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.ixbrl import annual_period_end, extract_facts
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling, OAMLocator
from global_markets.providers import (
    FundamentalsProvider,
    GlobalProviderError,
    MarketDataProvider,
    ProviderRegistry,
    append_source,
)

LEI = "5299000EAMGGBEYP7J33"
NOW = datetime.now(timezone.utc)
FRESH_END = (NOW.date() - timedelta(days=200)).replace(day=1)
STALE_END = NOW.date() - timedelta(days=700)


def _ixbrl(lei: str, end: date, *, revenue="357,263", profit="2,968") -> str:
    start = date(end.year - 1, end.month, end.day) + timedelta(days=1)
    pstart = date(start.year - 1, start.month, start.day)
    pend = date(end.year - 1, end.month, end.day)
    return f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>
<ix:header><ix:resources>
<xbrli:context id="cy"><xbrli:entity><xbrli:identifier scheme="http://standards.iso.org/iso/17442">{lei}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="py"><xbrli:entity><xbrli:identifier scheme="http://standards.iso.org/iso/17442">{lei}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>{pstart}</xbrli:startDate><xbrli:endDate>{pend}</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="ci"><xbrli:entity><xbrli:identifier scheme="http://standards.iso.org/iso/17442">{lei}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>{end}</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="seg"><xbrli:entity><xbrli:identifier scheme="http://standards.iso.org/iso/17442">{lei}</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="ifrs-full:SegmentsAxis">x:Cars</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="sek"><xbrli:measure>iso4217:SEK</xbrli:measure></xbrli:unit>
</ix:resources></ix:header>
<p><ix:nonFraction name="ifrs-full:Revenue" contextRef="cy" unitRef="sek" scale="6" decimals="-6" format="ixt:num-dot-decimal">{revenue}</ix:nonFraction></p>
<p><ix:nonFraction name="ifrs-full:Revenue" contextRef="py" unitRef="sek" scale="6" decimals="-6" format="ixt:num-dot-decimal">400,234</ix:nonFraction></p>
<p><ix:nonFraction name="ifrs-full:Revenue" contextRef="seg" unitRef="sek" scale="6" decimals="-6" format="ixt:num-dot-decimal">1</ix:nonFraction></p>
<p>(<ix:nonFraction name="ifrs-full:ProfitLoss" contextRef="cy" unitRef="sek" scale="6" decimals="-6" sign="-" format="ixt:num-dot-decimal">{profit}</ix:nonFraction>)</p>
<p><ix:nonFraction name="ifrs-full:Assets" contextRef="ci" unitRef="sek" scale="6" decimals="-6" format="ixt:num-comma-decimal">373.172</ix:nonFraction></p>
<p><ix:nonFraction name="ifrs-full:Equity" contextRef="ci" unitRef="sek" scale="6" decimals="-6" format="ixt:num-dot-decimal">148,378</ix:nonFraction></p>
<p><ix:nonFraction name="ifrs-full:Liabilities" contextRef="ci" unitRef="sek" scale="6" decimals="-6" format="ixt:num-dot-decimal">224,794</ix:nonFraction></p>
<p><ix:nonFraction name="ifrs-full:CashFlowsFromUsedInOperatingActivities" contextRef="cy" unitRef="sek" scale="6" format="ixt:num-dot-decimal">34,625</ix:nonFraction></p>
</body></html>"""


def _seed(**kw) -> GlobalCompany:
    base = dict(
        country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="VOLCAR.B",
        name="Volvo Car B", mic_code="XSTO", isin="SE0021628898",
    )
    base.update(kw)
    return GlobalCompany(**base)


# ---------------------------------------------------------------- extraction

def test_ixbrl_extracts_scaled_signed_facts_and_entity_lei():
    facts, entities = extract_facts([_ixbrl(LEI, date(2025, 12, 31))])
    assert entities == {LEI}
    by = {(f["dimensions"]["concept"], f["dimensions"]["period"], len(f["dimensions"])): float(f["value"]) for f in facts}
    assert by[("ifrs-full:Revenue", "2025-01-01/2025-12-31", 4)] == 357_263_000_000
    assert by[("ifrs-full:ProfitLoss", "2025-01-01/2025-12-31", 4)] == -2_968_000_000
    assert by[("ifrs-full:Assets", "2025-12-31", 4)] == 373_172_000_000
    assert annual_period_end(facts, ("ifrs-full:Revenue",)) == "2025-12-31"


def test_xbrl_json_exclusive_period_end_maps_to_correct_fiscal_year():
    # xBRL-JSON: FY2022 = 2022-01-01T00:00:00/2023-01-01T00:00:00.
    facts = [
        {"dimensions": {"concept": "ifrs-full:ProfitLoss", "period": "2022-01-01T00:00:00/2023-01-01T00:00:00"}, "value": "406"},
        {"dimensions": {"concept": "ifrs-full:ProfitLoss", "period": "2021-01-01T00:00:00/2022-01-01T00:00:00"}, "value": "330"},
        {"dimensions": {"concept": "ifrs-full:Assets", "period": "2023-01-01T00:00:00"}, "value": "8647"},
    ]
    E = esef.ESEFFundamentalsProvider
    assert E._duration_value(facts, date(2022, 12, 31)) == 406.0
    assert E._duration_value(facts, date(2022, 12, 31), previous=True) == 330.0
    assert E._instant_value(facts, date(2022, 12, 31)) == 8647.0
    assert esef._period_parts("2025-12-31") == (date(2025, 12, 31), date(2025, 12, 31))


# ------------------------------------------------------------ OAM provider

class _Locator(OAMLocator):
    oam = "se-test-oam"
    country = "SE"

    def __init__(self):
        pass

    def annual_filings(self, company, lei, legal_name):
        return [OAMFiling(oam=self.oam, document_id="FI:1", package_url="https://oam.example/1", landing_url="https://oam.example/1")]


def _oam_provider(monkeypatch, *, report_lei=LEI, end=None):
    provider = NationalOAMESEFProvider(locators=[_Locator()])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (LEI, "Volvo Car AB"))
    facts, entities = extract_facts([_ixbrl(report_lei, end or FRESH_END)])
    monkeypatch.setattr(provider, "package_facts", lambda filing: {"facts": facts, "entities": sorted(entities), "parsedAt": NOW.isoformat(), "reportFile": "r.xhtml"})
    return provider


def test_oam_provider_attaches_official_source_with_document_metadata(monkeypatch):
    result = _oam_provider(monkeypatch).enrich_fundamentals(_seed())
    official = [s for s in result.sources if is_official_fundamental_source(s)]
    assert len(official) == 1
    assert official[0].source_type == "official_regulatory_xbrl"
    assert official[0].source_id == "FI:1" and official[0].source_url == "https://oam.example/1"
    assert result.lei == LEI and result.filing_period_end == FRESH_END.isoformat()
    assert result.raw_provider_fields["oam_entity_lei_verified"] is True


def test_oam_report_for_different_entity_is_rejected(monkeypatch):
    provider = _oam_provider(monkeypatch, report_lei="549300BXVB4XRM8WSC73")
    with pytest.raises(GlobalProviderError, match="!= LEI"):
        provider.enrich_fundamentals(_seed())


def test_share_class_ticker_resolves_issuer_through_isin_not_name():
    class FakeGleif:
        def resolve_isin(self, isin, country=None):
            assert isin == "SE0021628898"
            return type("R", (), {"lei": LEI, "legal_name": "Volvo Car AB"})()

        def resolve_exact_legal_name(self, *a, **k):  # pragma: no cover - must not be used
            raise AssertionError("name fallback used although ISIN resolved")

    provider = NationalOAMESEFProvider(locators=[_Locator()])
    provider.gleif = FakeGleif()
    assert provider._resolve_lei(_seed(name="Volvo Car B")) == (LEI, "Volvo Car AB")


# ------------------------------------------------------- evidence semantics

class _Market(MarketDataProvider):
    provider_id = "market-test"

    def enrich_market(self, company):
        enriched = replace(company, price=25.0, price_observed_at=NOW.isoformat(), market_cap=7.4e10,
                           price_52w_high=30.0, price_52w_low=18.0, volatility_annualized_pct=35.0, pe=12.0)
        return append_source(enriched, SourceEvidence(provider="market-test", source_type="market_history", source_id="m", quality=0.9))


class _Vendor(FundamentalsProvider):
    provider_id = "vendor-test"

    def __init__(self, end=None):
        self.end = end or FRESH_END

    def enrich_fundamentals(self, company):
        enriched = replace(company, revenue=1.0, net_income=1.0, total_assets=2.0, total_liabilities=1.0,
                           total_equity=1.0, filing_period_end=self.end.isoformat(),
                           raw_provider_fields={**company.raw_provider_fields, "yahoo_fundamentals_supplement_only": True})
        return append_source(enriched, SourceEvidence(provider="yahoo-public-fundamentals-global",
                                                      source_type="public_vendor_financial_metrics", quality=0.7))


class _Official(FundamentalsProvider):
    provider_id = "official-test"

    def __init__(self, end):
        self.end = end
        self.calls = 0

    def enrich_fundamentals(self, company):
        self.calls += 1
        enriched = replace(company, revenue=10.0, revenue_prev=9.0, net_income=1.0, net_margin_pct=10.0,
                           total_assets=20.0, total_liabilities=10.0, total_equity=10.0,
                           operating_cash_flow=2.0, filing_period_end=self.end.isoformat())
        return append_source(enriched, SourceEvidence(provider="official-oam-se-test", source_type="official_regulatory_xbrl",
                                                      source_id="DOC-1", source_url="https://oam.example/1",
                                                      period_end=self.end.isoformat(), quality=0.95))


def _full(fundamentals: FundamentalsProvider) -> GlobalCompany:
    return fundamentals.enrich_fundamentals(_Market().enrich_market(_seed()))


def test_vendor_fallback_is_never_official_and_blocks():
    company = _full(_Vendor())
    evidence = evidence_agent(company)
    assert evidence.status == "BLOCK"
    assert "fundamental_source" in evidence.missing_critical
    contract = fundamental_evidence_contract(company)
    assert contract["isOfficial"] is False and contract["fundamental_source"] is None
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_SOURCE_UNAVAILABLE


def test_germany_complete_secondary_fundamentals_warns_not_blocks():
    company = _full(
        _Vendor()
    )
    company = replace(
        company,
        country="DE",
        exchange="FRANKFURT",
        currency="EUR",
        ticker="KGR",
        name="LEWAG HOLDING AG",
        mic_code="XFRA",
        isin="DE0006336001",
    )
    evidence = evidence_agent(company)
    assert evidence.status == "WARN"
    assert "fundamental_source" not in evidence.missing_critical
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_SOURCE_UNAVAILABLE
    assert "secondary_only_no_official_filing" in evidence.reasoning
    contract = fundamental_evidence_contract(company)
    assert contract["isOfficial"] is False


def test_vendor_source_type_with_official_words_is_still_not_official():
    tricky = SourceEvidence(provider="some-vendor", source_type="vendor_regulatory_filing_mirror")
    assert not is_official_fundamental_source(tricky)


def test_stale_official_still_trips_unchanged_stale_guard():
    company = _full(_Official(STALE_END))
    evidence = evidence_agent(company)
    assert evidence.status == "BLOCK"
    assert "fresh_fundamentals" in evidence.missing_critical
    assert "fundamental_source" not in evidence.missing_critical
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_STALE


def test_stale_official_with_newer_vendor_reports_official_stale_not_generic():
    provider = FallbackFundamentalsProvider(_Official(STALE_END), _Vendor())
    company = _full(provider)
    evidence = evidence_agent(company)
    assert evidence.status == "BLOCK" and "fundamental_source" in evidence.missing_critical
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_STALE
    assert "officialFundamentals=OFFICIAL_STALE" in evidence.reasoning


def test_fresh_official_satisfies_fundamental_gate():
    company = _full(_Official(FRESH_END))
    evidence = evidence_agent(company)
    assert "fundamental_source" not in evidence.missing_critical
    assert "fresh_fundamentals" not in evidence.missing_critical
    assert evidence.status in {"PASS", "WARN"}
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_CURRENT


# ------------------------------------------------------------------ cache

def test_official_provenance_survives_cache_roundtrip(tmp_path):
    PersistentFundamentalsProvider(_Official(FRESH_END), data_dir=str(tmp_path)).enrich_fundamentals(_seed())
    upstream = _Official(FRESH_END)
    cache = PersistentFundamentalsProvider(upstream, data_dir=str(tmp_path))
    restored = cache.enrich_fundamentals(_seed())
    assert upstream.calls == 0  # served from fresh official cache
    official = [s for s in restored.sources if is_official_fundamental_source(s)]
    assert official and official[0].source_id == "DOC-1" and official[0].source_url == "https://oam.example/1"
    stored = json.loads(next(tmp_path.rglob("latest.json")).read_text())
    assert stored["schemaVersion"] == 4
    assert stored["evidenceContract"]["isOfficial"] is True
    assert stored["evidenceContract"]["officialDocumentId"] == "DOC-1"


def test_cached_official_claim_without_official_source_is_not_honoured(tmp_path):
    PersistentFundamentalsProvider(_Official(FRESH_END), data_dir=str(tmp_path)).enrich_fundamentals(_seed())
    path = next(tmp_path.rglob("latest.json"))
    payload = json.loads(path.read_text())
    payload["sources"] = []  # numbers present, provenance lost
    path.write_text(json.dumps(payload))
    upstream = _Official(FRESH_END)
    result = PersistentFundamentalsProvider(upstream, data_dir=str(tmp_path)).enrich_fundamentals(_seed())
    assert upstream.calls == 1  # re-fetched instead of trusting the flag
    assert any(is_official_fundamental_source(s) for s in result.sources)


def test_vendor_refresh_cannot_overwrite_current_official_snapshot(tmp_path):
    PersistentFundamentalsProvider(_Official(FRESH_END), data_dir=str(tmp_path), fresh_hours=0).enrich_fundamentals(_seed())
    vendor_cache = PersistentFundamentalsProvider(_Vendor(), data_dir=str(tmp_path), fresh_hours=0)
    vendor_cache.upstream_id = "official-test"  # same slot, weaker refresh
    result = vendor_cache.enrich_fundamentals(_seed())
    assert any(is_official_fundamental_source(s) for s in result.sources)
    assert result.raw_provider_fields.get("fundamentals_official_preserved") is True
    stored = json.loads(next(tmp_path.rglob("latest.json")).read_text())
    assert stored["officialEvidence"] is True


# ------------------------------------------------ Android API path (route)

def _registry(fundamentals: FundamentalsProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_market("SE", "NASDAQ_STOCKHOLM", _Market())
    registry.register_fundamentals("SE", "NASDAQ_STOCKHOLM", fundamentals)
    return registry


@pytest.mark.parametrize("fundamentals,official", [(lambda: _Official(FRESH_END), True), (lambda: _Vendor(), False)])
def test_android_analyze_route_carries_canonical_evidence(monkeypatch, fundamentals, official):
    import global_routes
    from global_markets import service
    from global_api_server import app

    registry = _registry(fundamentals())
    monkeypatch.setattr(service, "build_registry", lambda: registry)
    monkeypatch.setattr(global_routes, "build_registry", lambda: registry)
    body = {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "VOLCAR.B", "name": "Volvo Car B",
            "currency": "SEK", "isin": "SE0021628898"}
    response = TestClient(app).post("/global/analyze", json=body)
    assert response.status_code == 200
    payload = response.json()
    contract = payload["fundamentalEvidence"]
    evidence = payload["evidence"]
    assert contract["isOfficial"] is official
    if official:
        # CI must fail if Android would see missing=fundamental_source while
        # official evidence is attached.
        assert "fundamental_source" not in evidence["missing_critical"]
        assert contract["fundamental_source"] == "official-oam-se-test"
        assert contract["officialDocumentId"] == "DOC-1"
        assert evidence["official_fundamental_status"] == STATUS_OFFICIAL_CURRENT
    else:
        assert evidence["status"] == "BLOCK"
        assert payload["governance"]["abstained"] is True
        assert evidence["official_fundamental_status"] == STATUS_OFFICIAL_SOURCE_UNAVAILABLE
