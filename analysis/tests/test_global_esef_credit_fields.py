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
