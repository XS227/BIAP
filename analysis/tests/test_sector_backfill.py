import pytest

import market_memory as mm
import sector_backfill as sb


@pytest.fixture(autouse=True)
def memory_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_MARKET_MEMORY_DB", str(tmp_path / "mm.db"))


PAYLOAD = {"instrumentIdentity": {"sector": {"cSecVal": "27 ", "lSecVal": "فلزات اساسي"}, "subSector": {"cSoSecVal": 2710, "lSoSecVal": "توليد آهن و فولاد پايه"},
                                  "yVal": "300", "cgrValCotTitle": "بازار اول"}}


def test_identity_becomes_a_sector_row_with_folded_letters():
    row = sb.row_from_identity("1", PAYLOAD, now="2026-11-06T00:00:00+00:00")
    assert row[:7] == ("1", "27", "فلزات اساسی", "2710", "توليد آهن و فولاد پايه".translate(sb._FA), "300", "بازار اول")
    assert sb.row_from_identity("2", {}) is None


def test_paper_type_decides_share_vs_fund_vs_bond():
    assert sb.kind_from_paper_type("300") == "stock" and sb.kind_from_paper_type("305") == "fund" and sb.kind_from_paper_type("306") == "bond"
    assert sb.kind_from_paper_type(None) is None


def test_backfill_is_idempotent_skips_mapped_and_survives_failures():
    calls = []
    def fetch(code):
        calls.append(code)
        if code == "bad":
            raise RuntimeError("502")
        return PAYLOAD
    res = sb.backfill(["1", "2", "bad"], fetch, interval=0, sleep=lambda s: None, log=lambda m: None)
    assert (res["done"], res["failed"]) == (2, 1) and set(mm.sector_map()) == {"1", "2"}
    calls.clear()
    res2 = sb.backfill(["1", "2"], fetch, interval=0, sleep=lambda s: None, log=lambda m: None)
    assert calls == [] and res2["skippedAlreadyMapped"] == 2
    assert mm.sector_map()["1"]["sectorName"] == "فلزات اساسی"


def test_universe_gets_the_sector_and_loses_funds_by_paper_type():
    import module_dataset as md
    mm.save_sectors([("a", "27", "فلزات اساسی", None, None, "300", None, "t"), ("b", "68", "صندوق", None, None, "305", None, "t")])
    rows = [{"code": "a", "symbol": "الف", "instrument_kind": "stock", "is_primary": 1, "sector": None}, {"code": "b", "symbol": "ب", "instrument_kind": "stock", "is_primary": 1, "sector": None},
            {"code": "c", "symbol": "ج", "instrument_kind": "stock", "is_primary": 1, "sector": None}]
    md._apply_sector_map(rows)
    assert rows[0]["sector"] == "فلزات اساسی" and rows[0]["instrument_kind"] == "stock" and rows[0]["is_primary"] == 1
    assert rows[1]["instrument_kind"] == "fund" and rows[1]["is_primary"] == 0
    assert rows[2]["sector"] is None  # unmapped stays as it is
