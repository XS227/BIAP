from datetime import date

from global_markets.esef import ESEFFundamentalsProvider


def _fact(concept, period, value):
    return {"dimensions": {"concept": concept, "period": period, "unit": "iso4217:GBP", "entity": "scheme:lei"}, "value": str(value)}


def _facts(flow_end="2026-01-01T00:00:00", flow_start="2025-01-01T00:00:00", instant="2026-01-01T00:00:00"):
    return [
        _fact("ifrs-full:ProfitLoss", f"{flow_start}/{flow_end}", 100),
        _fact("ifrs-full:Revenue", f"{flow_start}/{flow_end}", 900),
        _fact("ifrs-full:Assets", instant, 5000),
    ]


def _provider():
    return ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider)


def test_index_date_kept_when_facts_end_near_it():
    assert _provider().anchor_period(_facts(), date(2025, 12, 31)) == (date(2025, 12, 31), False)


def test_filing_date_index_is_corrected_to_the_facts_balance_date():
    # Aviva-like: indexed under the signing date, facts end 2025-12-31
    assert _provider().anchor_period(_facts(), date(2026, 3, 2)) == (date(2025, 12, 31), True)


def test_no_correction_without_a_balance_sheet_on_that_date():
    facts = [f for f in _facts() if "Assets" not in f["dimensions"]["concept"]]
    assert _provider().anchor_period(facts, date(2026, 3, 2)) == (date(2026, 3, 2), False)


def test_no_correction_when_the_gap_is_more_than_200_days():
    assert _provider().anchor_period(_facts(), date(2026, 9, 1)) == (date(2026, 9, 1), False)


def test_transition_period_filing_keeps_its_index_date():
    # Mediobanca-like: a 6-month flow ends at the index date; the last annual flow ended earlier
    facts = _facts(flow_start="2024-07-01T00:00:00", flow_end="2025-07-01T00:00:00", instant="2025-07-01T00:00:00") + [
        _fact("ifrs-full:ProfitLoss", "2025-07-01T00:00:00/2026-01-01T00:00:00", 40),
        _fact("ifrs-full:Assets", "2026-01-01T00:00:00", 5200),
    ]
    assert _provider().anchor_period(facts, date(2025, 12, 31)) == (date(2025, 12, 31), False)
