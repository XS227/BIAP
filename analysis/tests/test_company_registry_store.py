import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company_registry_store import CompanyRegistryStore, company_id_for
from instrument_classifier import CATEGORY_OPERATING_COMPANY, CATEGORY_RIGHTS_ISSUE, issuer_key


def test_company_ids_are_stable_and_deterministic():
    key = issuer_key("فولاد", "فولاد مبارکه", CATEGORY_OPERATING_COMPANY)
    assert company_id_for(key) == company_id_for(key)
    assert company_id_for(key).startswith("co_")
    assert company_id_for(key) != company_id_for("someotherkey")


def test_get_or_create_company_is_idempotent(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    key = issuer_key("فولاد", "فولاد مبارکه", CATEGORY_OPERATING_COMPANY)

    issuer_id_1, created_1 = reg.get_or_create_company(
        issuer_key_value=key, symbol="فولاد", name="فولاد مبارکه", category=CATEGORY_OPERATING_COMPANY,
        primary_instrument_code="100", run_id="run-1",
    )
    issuer_id_2, created_2 = reg.get_or_create_company(
        issuer_key_value=key, symbol="فولاد", name="فولاد مبارکه", category=CATEGORY_OPERATING_COMPANY,
        primary_instrument_code="100", run_id="run-2",
    )

    assert created_1 is True
    assert created_2 is False
    assert issuer_id_1 == issuer_id_2
    assert reg.company_count() == 1


def test_instrument_registry_never_drops_non_company_rows(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    reg.upsert_instrument(
        code="500", symbol="آکورد", name="صندوق سرمایه گذاری آکورد", market=None, paper_type="305",
        category="fund_etf", reason="fund keyword", issuer_id=None, is_duplicate=False, run_id="run-1",
    )
    assert reg.raw_instrument_count() == 1
    dist = reg.classification_distribution()
    assert dist.get("fund_etf") == 1
    # A fund is kept in the raw registry but never becomes a company.
    assert reg.company_count() == 0


def test_instrument_to_company_mapping_and_rights_issue_dedup(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    base_key = issuer_key("فولاد", "فولاد مبارکه", CATEGORY_OPERATING_COMPANY)
    issuer_id, created = reg.get_or_create_company(
        issuer_key_value=base_key, symbol="فولاد", name="فولاد مبارکه", category=CATEGORY_OPERATING_COMPANY,
        primary_instrument_code="100", run_id="run-1",
    )
    assert created is True

    rights_key = issuer_key("فولادح", "حق تقدم فولاد مبارکه", CATEGORY_RIGHTS_ISSUE)
    assert rights_key == base_key  # same underlying company

    reg.upsert_instrument(
        code="100", symbol="فولاد", name="فولاد مبارکه", market="TSE", paper_type="300",
        category=CATEGORY_OPERATING_COMPANY, reason="ordinary share", issuer_id=issuer_id,
        is_duplicate=False, run_id="run-1",
    )
    reg.upsert_instrument(
        code="101", symbol="فولادح", name="حق تقدم فولاد مبارکه", market=None, paper_type="400",
        category=CATEGORY_RIGHTS_ISSUE, reason="rights yVal", issuer_id=issuer_id,
        is_duplicate=False, run_id="run-1",
    )

    # Two instruments, one company: the rights issue must not inflate the count.
    assert reg.company_count() == 1
    instruments = reg.instruments_for_issuer(issuer_id)
    assert {row["code"] for row in instruments} == {"100", "101"}
    assert reg.primary_company_codes() == ["100"]


def test_duplicate_share_class_counted_separately_from_company(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    key = issuer_key("فولاد", "فولاد مبارکه", CATEGORY_OPERATING_COMPANY)
    issuer_id, _ = reg.get_or_create_company(
        issuer_key_value=key, symbol="فولاد", name="فولاد مبارکه", category=CATEGORY_OPERATING_COMPANY,
        primary_instrument_code="100", run_id="run-1",
    )
    reg.upsert_instrument(
        code="100", symbol="فولاد", name="فولاد مبارکه", market="TSE", paper_type="300",
        category=CATEGORY_OPERATING_COMPANY, reason="ordinary share", issuer_id=issuer_id,
        is_duplicate=False, run_id="run-1",
    )
    # A second instrument code that resolves to the same issuer_key is a duplicate share class.
    reg.upsert_instrument(
        code="199", symbol="فولاد", name="فولاد مبارکه", market="TSE", paper_type="300",
        category="duplicate_share_class", reason="duplicate issuer_key of 100", issuer_id=issuer_id,
        is_duplicate=True, run_id="run-1",
    )
    assert reg.company_count() == 1
    assert reg.duplicate_mapping_count() == 1
    assert reg.raw_instrument_count() == 2


def test_collection_runs_is_append_only(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    run_kwargs = dict(
        started_at="2026-09-17T00:00:00+00:00", completed_at="2026-09-17T00:05:00+00:00",
        source="test", discovered=10, attempted=5, succeeded=5, failed=0,
        new_unique_companies=3, re_enriched_companies=2, newly_classified_instruments=10,
        excluded_non_company=2, unresolved_unknown=1, total_unique_companies_before=0,
        total_unique_companies_after=3, total_enriched_before=0, total_enriched_after=5,
        duration_seconds=300.0, error_summary={"failedCount": 0, "sampleErrors": []},
    )
    run_id_1 = reg.record_run(**run_kwargs)
    run_id_2 = reg.record_run(**{**run_kwargs, "started_at": "2026-09-18T00:00:00+00:00"})

    assert run_id_1 != run_id_2
    runs = reg.list_runs(limit=10)
    assert len(runs) == 2
    ids = {row["run_id"] for row in runs}
    assert ids == {run_id_1, run_id_2}
    # Historical rows are never overwritten: both remain with their own started_at.
    started = {row["run_id"]: row["started_at"] for row in runs}
    assert started[run_id_1] == "2026-09-17T00:00:00+00:00"
    assert started[run_id_2] == "2026-09-18T00:00:00+00:00"


def test_collection_runs_has_no_mutable_updated_at_column(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    with reg._connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(collection_runs)").fetchall()}
    assert "updated_at" not in cols


def test_prune_orphaned_companies_removes_stale_misclassified_entries(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))

    # Simulate a run where a rights issue was wrongly classified as its own
    # insurance company (its name keyword-matched بیمه before rights detection
    # covered the abbreviated "ح." naming pattern).
    stale_key = issuer_key("حياتح", "ح.بیمه زندگی مفید", "insurance_company")
    stale_issuer_id, _ = reg.get_or_create_company(
        issuer_key_value=stale_key, symbol="حياتح", name="ح.بیمه زندگی مفید",
        category="insurance_company", primary_instrument_code="900", run_id="run-1",
    )
    reg.upsert_instrument(
        code="900", symbol="حياتح", name="ح.بیمه زندگی مفید", market=None, paper_type=None,
        category="insurance_company", reason="stale", issuer_id=stale_issuer_id, is_duplicate=False, run_id="run-1",
    )
    assert reg.company_count() == 1

    # A later run correctly reclassifies it as a rights issue linked to the real base company,
    # whose own ordinary-share instrument ("901") is the one that actually keeps the company alive.
    real_key = issuer_key("حیات", "بیمه زندگی مفید", "insurance_company")
    real_issuer_id, _ = reg.get_or_create_company(
        issuer_key_value=real_key, symbol="حیات", name="بیمه زندگی مفید",
        category="insurance_company", primary_instrument_code="901", run_id="run-2",
    )
    reg.upsert_instrument(
        code="901", symbol="حیات", name="بیمه زندگی مفید", market="TSE", paper_type="300",
        category="insurance_company", reason="ordinary share", issuer_id=real_issuer_id, is_duplicate=False, run_id="run-2",
    )
    reg.upsert_instrument(
        code="900", symbol="حياتح", name="ح.بیمه زندگی مفید", market=None, paper_type=None,
        category=CATEGORY_RIGHTS_ISSUE, reason="rights", issuer_id=real_issuer_id, is_duplicate=False, run_id="run-2",
    )

    assert reg.company_count() == 2  # stale row still present until pruned
    pruned = reg.prune_orphaned_companies()
    assert pruned == 1
    assert reg.company_count() == 1
    assert real_issuer_id != stale_issuer_id


def test_growth_by_date_reconstructs_history_from_run_log(tmp_path):
    reg = CompanyRegistryStore(str(tmp_path / "registry.sqlite3"))
    base_kwargs = dict(
        completed_at=None, source="test", discovered=1, attempted=1, succeeded=1, failed=0,
        newly_classified_instruments=1, excluded_non_company=0, unresolved_unknown=0,
        total_unique_companies_before=0, total_unique_companies_after=1,
        total_enriched_before=0, total_enriched_after=1, duration_seconds=1.0,
    )
    reg.record_run(started_at="2026-09-16T10:00:00+00:00", new_unique_companies=5, re_enriched_companies=0, **base_kwargs)
    reg.record_run(started_at="2026-09-17T10:00:00+00:00", new_unique_companies=3, re_enriched_companies=2, **base_kwargs)
    reg.record_run(started_at="2026-09-17T18:00:00+00:00", new_unique_companies=1, re_enriched_companies=4, **base_kwargs)

    growth = reg.growth_by_date()
    by_day = {row["day"]: row for row in growth}
    assert by_day["2026-09-16"]["new_companies"] == 5
    assert by_day["2026-09-17"]["new_companies"] == 4  # 3 + 1
    assert by_day["2026-09-17"]["re_enrichments"] == 6  # 2 + 4
    assert by_day["2026-09-17"]["runs"] == 2
