from datetime import date

from global_markets.esef import ESEFFundamentalsProvider, concept_is_relevant


def fact(concept, value, period, unit="iso4217:EUR"):
    return {
        "value": str(value),
        "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit},
    }


def test_extension_credit_concepts_are_conservative_and_mapped():
    p = ESEFFundamentalsProvider()
    end = date(2025, 12, 31)
    duration = "2025-01-01T00:00:00/2026-01-01T00:00:00"
    instant = "2026-01-01T00:00:00"
    facts = [
        fact("issuer:EBITDA", 120, duration),
        fact("issuer:CurrentFinancialDebt", 40, instant),
        fact("issuer:NoncurrentFinancialDebt", 60, instant),
        fact("issuer:RetainedEarnings", 35, instant),
        fact("ifrs-full:Revenue", 1000, duration),
    ]
    result = p.normalized_fields(facts, end)
    meta = result.pop("__normalization_meta__")
    assert result["ebitda"] == 120
    assert result["total_debt"] == 100
    assert result["retained_earnings"] == 35
    assert meta["ebitda_method"] == "direct_explicit_tag"
    assert meta["debt_method"] == "current_plus_noncurrent_borrowings"
    assert concept_is_relevant("issuer:EBITDA")
    assert not concept_is_relevant("issuer:Debt")


def test_ebitda_is_derived_only_from_operating_income_and_explicit_da():
    p = ESEFFundamentalsProvider()
    end = date(2025, 12, 31)
    duration = "2025-01-01T00:00:00/2026-01-01T00:00:00"
    facts = [
        fact("ifrs-full:ProfitLossFromOperatingActivities", 100, duration),
        fact("issuer:DepreciationAndAmortizationExpense", -20, duration),
        fact("ifrs-full:Revenue", 1000, duration),
    ]
    result = p.normalized_fields(facts, end)
    meta = result.pop("__normalization_meta__")
    assert result["ebitda"] == 120
    assert meta["ebitda_method"] == "derived_operating_income_plus_abs_depreciation_amortisation"


def test_liabilities_from_same_period_assets_minus_equity_when_direct_tag_absent():
    p = ESEFFundamentalsProvider()
    end = date(2025, 12, 31)
    instant = "2026-01-01T00:00:00"
    result = p.normalized_fields([
        fact("ifrs-full:Assets", 373172, instant),
        fact("ifrs-full:Equity", 148378, instant),
    ], end)
    assert result["total_liabilities"] == 224794
    assert result["__normalization_meta__"]["liabilities_method"] == "derived_assets_minus_equity_same_filing_period"


def test_liabilities_are_not_derived_from_inconsistent_balance_sheet():
    p = ESEFFundamentalsProvider()
    end = date(2025, 12, 31)
    instant = "2026-01-01T00:00:00"
    result = p.normalized_fields([
        fact("ifrs-full:Assets", 100, instant),
        fact("ifrs-full:Equity", 200, instant),
    ], end)
    assert result["total_liabilities"] is None


def test_incomplete_official_filing_does_not_invent_credit_inputs():
    """An OAM report with only headline IFRS facts must not imply full Agent 10 coverage."""
    p = ESEFFundamentalsProvider()
    end = date(2025, 12, 31)
    instant = "2026-01-01T00:00:00"
    duration = "2025-01-01T00:00:00/2026-01-01T00:00:00"
    result = p.normalized_fields([
        fact("ifrs-full:Assets", 373172, instant),
        fact("ifrs-full:Equity", 148378, instant),
        fact("ifrs-full:ProfitLossFromOperatingActivities", 303, duration),
        fact("ifrs-full:CashFlowsFromUsedInOperatingActivities", 34625, duration),
    ], end)
    assert result["total_liabilities"] == 224794
    assert result["ebitda"] is None
    assert result["total_debt"] is None
    assert result["free_cash_flow"] is None
    assert result["retained_earnings"] is None
