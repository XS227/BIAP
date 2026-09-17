"""Coverage for the classification-driven collection policy that replaced the
old CODAL-issuer-whitelist gate: TSETMC discovery -> instrument classification
-> issuer resolution -> dedup -> company enrichment eligibility.
"""
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import listed_company_ingestion as ingestion
from company_registry_store import CompanyRegistryStore
from listed_company_store import ListedCompanyStore


def _item(code: str, symbol: str, name: str | None = None, *, market=None, paper_type=None):
    data = {
        "code": code,
        "symbol": symbol,
        "name": name if name is not None else symbol,
        "market": market,
        "paper_type": paper_type,
        "source": "tsetmc",
    }
    return SimpleNamespace(code=code, symbol=symbol, name=data["name"], market=market, to_dict=lambda: dict(data))


def test_refresh_universe_classifies_whole_tape_not_just_codal_whitelist(tmp_path, monkeypatch):
    """A genuine bank/company must be collected even when it is absent from CODAL's directory.

    query_symbols() is the only upstream call this test needs to stub -- CODAL
    is no longer consulted by refresh_universe at all.
    """
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))

    operating = _item("1", "فولاد", "فولاد مبارکه اصفهان", market="TSE", paper_type="300")
    bank = _item("2", "وبملت", "بانک ملت", market="TSE", paper_type="300")
    fund = _item("3", "آکورد", "صندوق سرمایه گذاری آکورد", market=None, paper_type="300")
    bond = _item("4", "اخزا1", "اوراق خزانه اسلامی", market=None, paper_type=None)
    option = _item("5", "ضفولاد", "اختیار خرید فولاد", market=None, paper_type=None)
    rights = _item("6", "فولادح", "حق تقدم فولاد مبارکه اصفهان", market=None, paper_type="400")
    unknown = _item("7", "ZZ999", "", market=None, paper_type="999")

    monkeypatch.setattr(
        ingestion, "query_symbols",
        lambda limit=10000: [operating, bank, fund, bond, option, rights, unknown],
    )

    result = ingestion.refresh_universe(store, reg)

    assert result["strategy"] == "tsetmc-classification-registry"
    assert result["rawUniverseCount"] == 7
    # Only the two genuine companies are eligible for enrichment.
    assert set(result["_codes"]) == {"1", "2"}
    assert result["count"] == 2
    assert result["newUniqueCompanies"] == 2

    # Nothing is silently discarded: every instrument is kept, classified, in the raw registry.
    assert reg.raw_instrument_count() == 7
    dist = reg.classification_distribution()
    assert dist["operating_company"] == 1
    assert dist["bank"] == 1
    assert dist["fund_etf"] == 1
    assert dist["bond_debt"] == 1
    assert dist["option_derivative"] == 1
    assert dist["rights_issue"] == 1
    assert dist["unknown"] == 1

    # The rights issue is linked to فولاد's issuer, not counted as its own company.
    assert reg.company_count() == 2
    fund_row = reg.get_instrument("3")
    assert fund_row["issuer_id"] is None


def test_refresh_universe_deduplicates_repeated_issuer_across_instruments(tmp_path, monkeypatch):
    """Two different instrument codes resolving to the same company must not inflate the company count."""
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))

    primary = _item("10", "فولاد", "فولاد مبارکه اصفهان", market="TSE", paper_type="300")
    duplicate = _item("11", "فولاد", "فولاد مبارکه اصفهان", market="TSE", paper_type="300")

    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: [primary, duplicate])
    result = ingestion.refresh_universe(store, reg)

    assert reg.company_count() == 1
    assert reg.duplicate_mapping_count() == 1
    # Lowest code (sorted deterministically) wins as the primary enrichment target.
    assert result["_codes"] == ["10"]
    dup_row = reg.get_instrument("11")
    assert dup_row["category"] == "duplicate_share_class"


def test_refresh_universe_empty_live_universe_falls_back_to_registry(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))

    operating = _item("1", "فولاد", "فولاد مبارکه اصفهان", market="TSE", paper_type="300")
    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: [operating])
    ingestion.refresh_universe(store, reg)

    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: [])
    result = ingestion.refresh_universe(store, reg)

    assert result["strategy"] == "empty-live-universe-fallback"
    assert result["_codes"] == ["1"]
