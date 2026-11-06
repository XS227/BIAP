"""P2.2: Equinor-style current-asset subtotals (no held-for-sale group) and dividend per share from ESEF facts."""
from datetime import date

from global_markets.esef import ESEFFundamentalsProvider

END = date(2025, 12, 31)
DUR = "2025-01-01T00:00:00/2026-01-01T00:00:00"
INST = "2026-01-01T00:00:00"
CA_ALT = "ifrs-full:CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners"
CL_ALT = "ifrs-full:CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale"
HFS_A = "ifrs-full:NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners"
HFS_L = "ifrs-full:LiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale"


def fact(concept, value, period, unit="iso4217:USD"):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit}}


def norm(*facts):
    return ESEFFundamentalsProvider().normalized_fields([fact("ifrs-full:Revenue", 1000, DUR), *facts], END)


def test_alt_current_subtotals_used_when_primary_absent_and_no_held_for_sale_group():
    r = norm(fact(CA_ALT, 500, INST), fact(CL_ALT, 300, INST))
    meta = r["__normalization_meta__"]
    assert r["current_assets"] == 500 and r["current_liabilities"] == 300
    assert meta["current_assets_method"] == "subtotal_other_than_held_for_sale_no_group_tagged"


def test_primary_tag_wins():
    r = norm(fact("ifrs-full:CurrentAssets", 700, INST), fact(CA_ALT, 500, INST))
    assert r["current_assets"] == 700


def test_alt_not_used_when_held_for_sale_group_exists():
    r = norm(fact(CA_ALT, 500, INST), fact(HFS_A, 40, INST), fact(CL_ALT, 300, INST), fact(HFS_L, 10, INST))
    assert r["current_assets"] is None and r["current_liabilities"] is None


def test_zero_held_for_sale_counts_as_no_group():
    r = norm(fact(CA_ALT, 500, INST), fact(HFS_A, 0, INST))
    assert r["current_assets"] == 500


def test_dividend_per_share_recognised_then_declared():
    rec = "ifrs-full:DividendsRecognisedAsDistributionsToOwnersPerShare"
    dec = "ifrs-full:DividendsProposedOrDeclaredBeforeFinancialStatementsAuthorisedForIssueButNotRecognisedAsDistributionToOwnersPerShare"
    r = norm(fact(rec, 1.2, DUR), fact(dec, 1.5, DUR))
    assert r["dividend_per_share"] == 1.2 and r["__normalization_meta__"]["dividend_per_share_basis"] == "recognised_in_year"
    r = norm(fact(dec, 1.5, DUR))
    assert r["dividend_per_share"] == 1.5 and r["__normalization_meta__"]["dividend_per_share_basis"] == "declared_not_recognised"
    assert "dividend_per_share" not in norm()          # absent key, never a guess


def test_de_reviewed_record_accepts_dividend_and_ffo():
    from global_markets.german_reviewed_reports import GermanReviewedAnnualReportProvider
    from global_markets.models import GlobalCompany
    row = {"isin": "DE0007164600", "ticker": "SAP", "periodEnd": "2025-12-31", "sourceUrl": "https://example.com/r.pdf", "currency": "EUR",
           "fundamentals": {"revenue": 100.0, "dividend_per_share": 2.5, "ffo": 40.0, "ffo_method": "reviewed:interest_paid_from_cash_flow"}}
    prov = GermanReviewedAnnualReportProvider(registry={"DE0007164600": row})
    out = prov.enrich_fundamentals(GlobalCompany(country="DE", exchange="XETRA", currency="EUR", ticker="SAP", name="SAP", isin="DE0007164600"))
    assert out.dividend_per_share == 2.5
    assert out.raw_provider_fields["agent10_ffo"] == 40.0 and out.raw_provider_fields["agent10_ffo_method"].startswith("reviewed:")
