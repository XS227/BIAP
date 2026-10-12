"""Official-filing field provenance: genuinely untagged vs tagged-but-withheld."""
from datetime import date

from global_markets.analysis_ledger import missing_reasons
from global_markets.esef import ESEFFundamentalsProvider

END = date(2025, 12, 31)
INSTANT = "2025-12-31"
YEAR = "2025-01-01/2025-12-31"


def fact(concept, value, period=INSTANT, unit="iso4217:SEK", **dims):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit, **dims}}


def status(facts):
    return ESEFFundamentalsProvider().normalized_fields(facts, END)["__normalization_meta__"]["field_status"]


def test_nothing_tagged_is_reported_as_not_tagged():
    s = status([fact("ifrs-full:Revenue", 100, YEAR)])
    assert s == {
        "shares_outstanding": "not_tagged_in_filing",
        "ebitda": "operating_income_not_tagged",
        "total_debt": "not_tagged_borrowings",
    }


def test_plain_outstanding_and_issued_fallback_are_labelled():
    assert status([fact("ifrs-full:NumberOfSharesOutstanding", 5, unit="xbrli:shares")])["shares_outstanding"] == "extracted_plain_outstanding"
    assert status([fact("ifrs-full:NumberOfSharesIssued", 5, unit="xbrli:shares")])["shares_outstanding"] == "extracted_issued_single_class_fallback"


def test_per_class_and_extension_share_tags_are_extraction_decisions_not_gaps():
    per_class = fact("ifrs-full:NumberOfSharesOutstanding", 5, unit="xbrli:shares", **{"ifrs-full:ClassesOfOrdinarySharesAxis": "x:AMember"})
    assert status([per_class])["shares_outstanding"] == "tagged_per_class_or_ambiguous_not_summed"
    ext = fact("abc:NumberOfSharesSeriesB", 5, unit="xbrli:shares")
    assert status([ext])["shares_outstanding"] == "tagged_issuer_extension_concept_not_mapped"


def test_ebitda_status_distinguishes_missing_da_from_impairment_inclusive_da():
    op = fact("ifrs-full:ProfitLossFromOperatingActivities", 50, YEAR)
    assert status([op])["ebitda"] == "not_tagged_depreciation_amortisation"
    impaired = fact("ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 9, YEAR)
    assert status([op, impaired])["ebitda"] == "tagged_da_impairment_inclusive_only_not_used"
    pure = fact("ifrs-full:DepreciationAndAmortisationExpense", 9, YEAR)
    r = ESEFFundamentalsProvider().normalized_fields([op, pure], END)
    assert r["ebitda"] == 59 and r["__normalization_meta__"]["field_status"]["ebitda"] == "extracted"


def test_debt_component_larger_than_total_is_withheld_not_guessed():
    facts = [
        fact("ifrs-full:LongtermBorrowings", 984),
        fact("ifrs-full:NoncurrentPortionOfNoncurrentBondsIssued", 2835),
    ]
    r = ESEFFundamentalsProvider().normalized_fields(facts, END)
    assert r["total_debt"] is None
    assert r["__normalization_meta__"]["debt_method"] == "withheld:component_exceeds_borrowings_total"
    assert r["__normalization_meta__"]["field_status"]["total_debt"] == "tagged_components_inconsistent_withheld"


def test_consistent_borrowings_are_extracted():
    facts = [fact("ifrs-full:LongtermBorrowings", 5461), fact("ifrs-full:NoncurrentPortionOfNoncurrentBondsIssued", 793)]
    r = ESEFFundamentalsProvider().normalized_fields(facts, END)
    assert r["total_debt"] == 5461
    assert r["__normalization_meta__"]["field_status"]["total_debt"] == "extracted"


def _result(field_status):
    return {
        "company": {
            "currency": "SEK", "reporting_currency": "SEK", "price": 10.0,
            "raw_provider_fields": {"oam_credit_extraction": {"field_status": field_status}} if field_status else {},
        },
        "fundamentalEvidence": {"fundamental_source": "official-oam"},
    }


def test_missing_reasons_cite_filing_status():
    r = missing_reasons(_result({"shares_outstanding": "not_tagged_in_filing"}), ["market_cap"])
    assert r["market_cap"] == "no_share_count:not_tagged_in_filing;exchange_feed_has_no_market_cap"
    r = missing_reasons(_result({"shares_outstanding": "tagged_per_class_or_ambiguous_not_summed"}), ["market_cap"])
    assert "tagged_per_class_or_ambiguous_not_summed" in r["market_cap"]
    r = missing_reasons(_result(None), ["market_cap"])
    assert "snapshot_predates_field_status" in r["market_cap"]
