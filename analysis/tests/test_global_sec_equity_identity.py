"""Total equity is cross-checked against the balance-sheet identity.

Agilent FY2025 companyfacts carries accumulated OCI (-226m) under the
NCI-inclusive equity tag, while parent equity is 6,741m and
assets 12,727m = liabilities 5,986m + 6,741m.
"""
from global_markets.models import GlobalCompany
from global_markets.sec_edgar import SECEdgarFundamentalsProvider


def _concept(value, *, end="2025-10-31", start=None):
    row = {"form": "10-K", "fp": "FY", "fy": 2025, "end": end, "filed": "2025-12-22", "val": value}
    if start:
        row["start"] = start
    return {"units": {"USD": [row]}}


def _enrich(monkeypatch, facts):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1090872)
    monkeypatch.setattr(provider, "_get_json", lambda url: {"entityName": "AGILENT TECHNOLOGIES, INC.", "facts": {"us-gaap": facts}})
    company = GlobalCompany(country="US", exchange="NYSE", mic_code="XNYS", currency="USD", ticker="A", name="Agilent Technologies")
    return provider.enrich_fundamentals(company)


def _base():
    return {
        "Revenues": _concept(6_948_000_000, start="2024-11-01"),
        "NetIncomeLoss": _concept(1_303_000_000, start="2024-11-01"),
        "Assets": _concept(12_727_000_000),
        "StockholdersEquity": _concept(6_741_000_000),
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(-226_000_000),
    }


def test_mistagged_nci_total_loses_to_parent_total_that_ties(monkeypatch):
    facts = {**_base(), "Liabilities": _concept(5_986_000_000)}
    assert _enrich(monkeypatch, facts).total_equity == 6_741_000_000


def test_negative_nci_total_without_liabilities_never_overrides_positive_parent(monkeypatch):
    enriched = _enrich(monkeypatch, _base())
    assert enriched.total_equity == 6_741_000_000
    assert enriched.total_liabilities == 5_986_000_000


def test_consistent_nci_inclusive_total_is_still_preferred(monkeypatch):
    facts = {**_base(), "Liabilities": _concept(5_800_000_000),
             "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(6_927_000_000)}
    assert _enrich(monkeypatch, facts).total_equity == 6_927_000_000


def test_revenue_tagged_including_assessed_tax_is_read(monkeypatch):
    # AAON FY2025 tags its top line only as ...IncludingAssessedTax.
    facts = {**_base(), "Liabilities": _concept(5_986_000_000)}
    facts.pop("Revenues")
    facts["RevenueFromContractWithCustomerIncludingAssessedTax"] = _concept(1_442_076_000, start="2024-11-01")
    assert _enrich(monkeypatch, facts).revenue == 1_442_076_000


def test_excluding_assessed_tax_revenue_wins_a_same_period_tie(monkeypatch):
    facts = {**_base(), "Liabilities": _concept(5_986_000_000)}
    facts["RevenueFromContractWithCustomerExcludingAssessedTax"] = _concept(6_900_000_000, start="2024-11-01")
    facts["RevenueFromContractWithCustomerIncludingAssessedTax"] = _concept(7_100_000_000, start="2024-11-01")
    facts.pop("Revenues")
    assert _enrich(monkeypatch, facts).revenue == 6_900_000_000
