from datetime import date, datetime, timezone

from global_markets.esef import ESEFFundamentalsProvider
from global_markets.evidence_contract import fundamental_evidence_contract
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.sector_supplement import SECSectorSupplementProvider
from global_markets.providers import FundamentalsProvider

DUR = "2025-01-01/2025-12-31"
INST = "2025-12-31"


def fact(concept, value, period, unit="iso4217:USD"):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit}}


def shell_facts():
    return [
        fact("ifrs-full:Revenue", 266886e6, DUR),
        fact("ifrs-full:ProfitLoss", 18119e6, DUR),
        fact("ifrs-full:ProfitLossBeforeTax", 29756e6, DUR),
        fact("ifrs-full:InterestExpense", 4671e6, DUR),
        fact("ifrs-full:CashFlowsFromUsedInOperatingActivities", 42863e6, DUR),
        fact("ifrs-full:LongtermBorrowings", 66515e6, INST),
        fact("ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", 9128e6, INST),
        fact("ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 25299e6, DUR),
        fact("ifrs-full:PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities", 18947e6, DUR),
    ]


def norm():
    p = ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider)
    r = p.normalized_fields(shell_facts(), date(2025, 12, 31))
    return r, r.pop("__normalization_meta__")


def test_shell_debt_tags_are_mapped_as_sum_of_current_and_noncurrent():
    r, meta = norm()
    assert r["total_debt"] == 75643e6 and meta["debt_method"] == "current_plus_noncurrent_borrowings"
    assert r["reporting_currency"] == "USD"


def test_ambiguous_ebitda_and_fcf_inputs_are_never_guessed_but_are_disclosed():
    r, meta = norm()
    assert r["ebitda"] is None and r["operating_income"] is None and r["free_cash_flow"] is None
    excluded = meta["excluded_candidates"]
    assert any("DepreciationAmortisationAndImpairment" in k for k in excluded)
    assert any("PurchaseOfOtherLongtermAssets" in k for k in excluded)


def test_limitations_name_tagged_but_unused_lines():
    c = GlobalCompany(
        country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="SHELL PLC", reporting_currency="USD",
        filing_period_end="2025-12-31", interest_expense=1.0,
        raw_provider_fields={"oam_credit_extraction": {"excluded_candidates": {"shel:CashOutflowForTotalCashCapitalExpenditure": 1.0}}},
        sources=[SourceEvidence(provider="official-oam-gb-fca-nsm", source_type="official_regulatory_xbrl", period_end="2025-12-31", provenance_status="official")],
    )
    out = fundamental_evidence_contract(c, now=datetime(2026, 10, 12, tzinfo=timezone.utc))["limitations"]
    assert any("tagged but not used" in x and "CashOutflowForTotalCashCapitalExpenditure" in x for x in out)


def test_freshness_detail_separates_period_filing_and_price_dates():
    c = GlobalCompany(
        country="US", exchange="NASDAQ", currency="USD", ticker="TSLA", name="Tesla, Inc.",
        filing_period_end="2025-12-31", filing_observed_at="2026-01-29", price_observed_at="2026-10-09T20:00:00+00:00",
        sources=[SourceEvidence(provider="sec-edgar", source_type="official_filing_xbrl", period_end="2025-12-31", provenance_status="official")],
    )
    out = fundamental_evidence_contract(c, now=datetime(2026, 10, 12, tzinfo=timezone.utc))
    d = out["freshnessDetail"]
    assert out["officialStatus"] == "OFFICIAL_CURRENT"
    assert out["freshness"] == "last_annual"  # never "current" for a ~285-day-old filing
    assert d["periodAgeDays"] == 285 and d["filingDate"] == "2026-01-29" and d["priceAgeDays"] == 3
    assert d["thresholds"] == {"lastAnnualAfterDays": 200, "staleAfterDays": 550}
    assert "not current-quarter data" in d["statement"]


class _Inner(FundamentalsProvider):
    provider_id = "inner"

    def __init__(self, sector=None):
        self.sector = sector

    def enrich_fundamentals(self, company):
        from dataclasses import replace
        return replace(company, sector=self.sector)


class _Sec:
    def __init__(self, found):
        self.found, self.calls = found, 0

    def sic_sector(self, company):
        self.calls += 1
        return self.found


def _co():
    return GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="SHELL PLC")


def test_sector_supplement_fills_only_missing_sector_with_provenance():
    sec = _Sec({"sector": "Mining & Energy", "industry": "Crude Petroleum & Natural Gas", "sic": 1311, "cik": 1306965,
                "entityName": "Shell plc", "source": "sec-sic", "sourceUrl": "https://data.sec.gov/submissions/CIK0001306965.json"})
    out = SECSectorSupplementProvider(_Inner(), sec).enrich_fundamentals(_co())
    assert out.sector == "Mining & Energy" and out.raw_provider_fields["sector_source"] == "sec-sic"
    assert "not GICS" in out.raw_provider_fields["sector_provenance"]["classification"]
    kept = SECSectorSupplementProvider(_Inner("Utilities"), sec).enrich_fundamentals(_co())
    assert kept.sector == "Utilities"


def test_sector_supplement_leaves_sector_empty_when_identity_unverified():
    sec = _Sec(None)
    prov = SECSectorSupplementProvider(_Inner(), sec)
    assert prov.enrich_fundamentals(_co()).sector is None
    prov.enrich_fundamentals(_co())
    assert sec.calls == 1  # negative result cached, no repeated SEC lookups


def test_cross_currency_listing_does_not_derive_pe_without_an_fx_rate(monkeypatch):
    """Without a usable reference rate a USD EPS is never divided into a GBP price.
    (With a rate the figure is converted and labelled: see test_global_s13_engine.)"""
    from global_markets import service

    class NoRate:
        def __init__(self, *a, **k):
            pass

        def rate(self, base, quote):
            raise RuntimeError("no rate")

    monkeypatch.setattr(service, "ECBReferenceFXProvider", NoRate)
    c = GlobalCompany(country="GB", exchange="LSE", currency="GBP", reporting_currency="USD", ticker="SHEL",
                      name="SHELL PLC", price=37.9, eps=3.03)
    assert service._derive_metrics(c).pe is None
