"""Reviewed issuer D&A mapping: extension-tagged cash-flow lines summed, impairments excluded."""
from __future__ import annotations

from datetime import date

from global_markets.esef import ESEFFundamentalsProvider

LEI = "969500A1YF1XUYYXS284"
OTHER = "2138001AD31KKD29Z495"


def _fact(concept, value, lei=LEI, period="2025-01-01/2025-12-31"):
    return {"dimensions": {"concept": concept, "entity": f"scheme:{lei}", "period": period, "unit": "iso4217:EUR"},
            "value": str(value)}


def _facts(lei=LEI, with_second=True):
    facts = [
        _fact("ifrs-full:ProfitLossFromOperatingActivities", 6_699_000_000, lei),
        _fact("schneiderelectric:AdjustmentsForDepreciationOfPropertyPlantAndEquipment", 871_000_000, lei),
        _fact("ifrs-full:AdjustmentsForImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 53_000_000, lei),
    ]
    if with_second:
        facts.append(_fact("schneiderelectric:AdjustmentsForDepreciationOfIntangibleAssetsOtherThanGoodwill",
                           781_000_000, lei))
    return facts


def _normalise(facts):
    provider = ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider)
    return provider.normalized_fields(facts, date(2025, 12, 31))


def test_reviewed_lines_sum_to_ebitda_without_impairment():
    out = _normalise(_facts())
    assert out["ebitda"] == 6_699_000_000 + 871_000_000 + 781_000_000


def test_mapping_not_applied_when_a_reviewed_line_is_missing():
    assert _normalise(_facts(with_second=False)).get("ebitda") is None


def test_mapping_not_applied_to_other_issuers():
    assert _normalise(_facts(lei=OTHER)).get("ebitda") is None


def test_mapping_not_applied_to_a_different_fiscal_year():
    facts = _facts()
    for f in facts:
        f["dimensions"]["period"] = "2026-01-01/2026-12-31"
    provider = ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider)
    assert provider.normalized_fields(facts, date(2026, 12, 31)).get("ebitda") is None


def test_kitron_reviewed_line_gives_standard_ebitda():
    kit = "5967007LIEEXZXIG6009"
    facts = [
        _fact("ifrs-full:ProfitLossFromOperatingActivities", 64_500_000, kit),
        _fact("ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
              18_600_000, kit),
    ]
    out = _normalise(facts)
    assert out["ebitda"] == 83_100_000
    assert "nonstandard_metrics" not in out["__normalization_meta__"]
