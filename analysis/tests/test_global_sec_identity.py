"""Cross-listed SEC identity and annual-row selection for Canadian filers."""
from __future__ import annotations

from global_markets import sec_identity
from global_markets.models import GlobalCompany
from global_markets.sec_crosslisted_gaap import SECCrossListedUSGAAPFundamentalsProvider as GAAP
from global_markets.sec_identity import IssuerNames, cik_by_name, identity_matches, sec_core


def test_sec_header_artefacts_are_normalized():
    assert sec_core("BANK OF MONTREAL /CAN/") == sec_core("Bank of Montreal")
    assert sec_core("CANADIAN PACIFIC KANSAS CITY LTD/CN") == sec_core("Canadian Pacific Kansas City Limited")
    assert sec_core("Bank of Nova Scotia (The)") == sec_core("BANK OF NOVA SCOTIA")
    assert sec_core("The Toronto-Dominion Bank") == sec_core("TORONTO DOMINION BANK")
    assert sec_core("Core Natural Resources, Inc.") != sec_core("Canadian National Railway Co")


def test_gleif_name_is_consulted_only_when_local_names_fail(monkeypatch):
    calls = []
    monkeypatch.setattr(sec_identity, "gleif_legal_name", lambda c: calls.append(c.isin) or "THE TORONTO-DOMINION BANK")
    td = GlobalCompany(country="CA", exchange="TSX", currency="CAD", ticker="TD", name="TD", isin="CA8911605092")
    names = IssuerNames(td)
    assert identity_matches("TORONTO DOMINION BANK", names) and calls == ["CA8911605092"]
    ry = IssuerNames(GlobalCompany(country="CA", exchange="TSX", currency="CAD", ticker="RY", name="Royal Bank of Canada", isin="CA7800871021"))
    assert identity_matches("ROYAL BANK OF CANADA", ry) and calls == ["CA8911605092"]


def test_cik_by_name_requires_a_unique_filer(monkeypatch):
    monkeypatch.setattr(sec_identity, "_titles", {sec_core("CANADIAN NATIONAL RAILWAY CO"): {16868}, sec_core("ACME CORP"): {1, 2}})
    assert cik_by_name(None, ["Canadian National Railway Company"]) == 16868
    assert cik_by_name(None, ["Acme Corporation"]) is None


def _row(form, end, val, fp="FY", start=None):
    return {"form": form, "fp": fp, "end": end, "start": start, "val": val, "filed": end}


def test_year_end_6k_only_for_filers_without_annual_forms():
    only_6k = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        _row("6-K", "2025-12-31", 10, start="2025-01-01"), _row("6-K", "2025-09-30", 3, start="2025-07-01")]}}}}}
    rows = GAAP._annual_rows(GAAP._facts(only_6k)["NetIncomeLoss"])
    assert [r["val"] for r in rows] == [10]  # a 3-month span is rejected even when labelled FY
    mixed = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        _row("10-K", "2025-12-31", 7, start="2025-01-01"), _row("6-K", "2026-06-30", 9, start="2025-07-01")]}}}}}
    assert [r["val"] for r in GAAP._annual_rows(GAAP._facts(mixed)["NetIncomeLoss"])] == [7]


def test_most_recent_tag_series_wins():
    gaap = {
        "Revenues": {"units": {"USD": [_row("40-F", "2023-12-31", 7)]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [_row("10-K", "2025-12-31", 11)]}},
    }
    series = GAAP._annual_series(gaap, ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"))
    assert series[0]["end"] == "2025-12-31"
