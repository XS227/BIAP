import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company_registry_store import CompanyRegistryStore
from listed_company_store import ListedCompanyStore
from migrate_company_registry import run_migration


def _seed_production_like_db(db_path: str) -> None:
    store = ListedCompanyStore(db_path)
    with store._connect() as conn:
        conn.executescript(
            """
            INSERT INTO listed_companies
                (code,symbol,name_fa,market,source_universe,source_updated_at,provenance_json,created_at,updated_at)
            VALUES
                ('1','فولاد','فولاد مبارکه اصفهان','TSE','listed-company-tsetmc-equity','2026-01-01','{}','2026-01-01','2026-01-01'),
                ('2','آکورد','صندوق س.آکورد سهامی','IFB','listed-company-tsetmc-codal','2026-01-01','{}','2026-01-01','2026-01-01'),
                ('3','آبارا07','مرابحه صنایع پمپ آبارا070224','IFB','listed-company-tsetmc-equity','2026-01-01','{}','2026-01-01','2026-01-01'),
                ('4','نامشخص','','IFB','tsetmc','2026-01-01','{}','2026-01-01','2026-01-01')
            """
        )
    # "فولاد" (code 1) is already enriched -- migration must never touch this.
    store.save_enriched(
        "1",
        {"ticker": "فولاد", "name_fa": "فولاد مبارکه اصفهان", "data_available": {"codal": True}, "market": {"price": 999}},
        provenance={"builder": "pre-migration-test"},
    )


def test_migration_preserves_enriched_data_and_row_count(tmp_path):
    db_path = str(tmp_path / "listed.sqlite3")
    _seed_production_like_db(db_path)

    store = ListedCompanyStore(db_path)
    before_enriched = store.get("1")
    assert before_enriched["company"]["market"]["price"] == 999
    raw_before = store.count()

    report = run_migration(db_path)

    store_after = ListedCompanyStore(db_path)
    after_enriched = store_after.get("1")
    # The actual enrichment payload (company_json) is never touched by migration/refresh.
    assert after_enriched["company"]["market"]["price"] == 999
    assert after_enriched["company"]["name_fa"] == "فولاد مبارکه اصفهان"
    # Enrichment provenance also survives a routine universe refresh, not just company_json.
    assert after_enriched["provenance"]["builder"] == "pre-migration-test"
    assert store_after.count() == raw_before  # no rows dropped or fabricated

    assert report["rawInstruments"] == 4
    # فولاد (enriched) + row 4 (blank name, but market=IFB is a verified equity-flow
    # signal so it conservatively counts as an operating_company); fund/bond excluded.
    assert report["genuineUniqueCompanies"] == 2
    assert report["enrichedUniqueCompanies"] == 1
    assert report["unenrichedUniqueCompanies"] == 1
    assert report["nonCompanyInstruments"] >= 2  # fund + bond at minimum


def test_migration_is_idempotent(tmp_path):
    db_path = str(tmp_path / "listed.sqlite3")
    _seed_production_like_db(db_path)

    first = run_migration(db_path)
    second = run_migration(db_path)

    assert first["genuineUniqueCompanies"] == second["genuineUniqueCompanies"]
    reg = CompanyRegistryStore(db_path)
    assert reg.company_count() == first["genuineUniqueCompanies"]
    # Each run still appends its own audit row (a re-run is a real, auditable event).
    runs = reg.list_runs(limit=10)
    assert len(runs) == 2
    assert all(row["source"] == "migration" for row in runs)


def test_migration_classifies_fund_and_bond_out_of_company_dataset(tmp_path):
    db_path = str(tmp_path / "listed.sqlite3")
    _seed_production_like_db(db_path)
    run_migration(db_path)

    reg = CompanyRegistryStore(db_path)
    fund_row = reg.get_instrument("2")
    bond_row = reg.get_instrument("3")
    assert fund_row["category"] == "fund_etf"
    assert bond_row["category"] == "bond_debt"
    assert fund_row["issuer_id"] is None
    assert bond_row["issuer_id"] is None
