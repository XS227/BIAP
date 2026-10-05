#!/usr/bin/env python3
"""(Re-)classify the full raw instrument tape and (re)populate the
company/issuer registry, without touching any existing enriched company data.

Reads every instrument code known from either of two sources and merges them
(``instrument_registry`` takes priority when a code is in both, since it may
hold richer/fresher symbol-name-market-paper_type data from a live TSETMC
fetch than the older ``listed_companies`` table ever captured):

- ``instrument_registry`` -- the full raw universe as already classified by
  any previous run (first migration or a live daily refresh). Reclassifying
  from here (rather than only ever fetching live) means classifier
  improvements apply retroactively without depending on TSETMC connectivity,
  which this host's network to TSETMC is not always reliable for.
- ``listed_companies`` -- the original pre-registry raw TSETMC universe (also
  covers any code that, for whatever reason, never made it into
  instrument_registry).

Each row is classified, issuers are resolved, duplicates are deduplicated,
and results are written via the exact same classification/dedup path used by
the live daily worker (listed_company_ingestion._classify_and_register).
``company_json`` (the enriched payload) is never read or modified by this
script -- it only adds ``source_universe``/``provenance_json`` metadata on
company rows via the normal ``upsert_universe`` path, which explicitly
COALESCEs around enrichment fields.

Safe to run multiple times: instrument/company upserts are idempotent
(keyed by code / deterministic issuer_id), a stale company_registry entry
that no instrument still backs is pruned automatically, and each run still
appends its own row to the append-only ``collection_runs`` audit log, since a
(re)classification pass is itself a real, auditable event.

Usage:
    python3 migrate_company_registry.py [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from company_registry_store import CompanyRegistryStore
from listed_company_ingestion import _classify_and_register
from listed_company_store import DEFAULT_LISTED_COMPANY_DB, ListedCompanyStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_raw_rows(target: ListedCompanyStore, registry: CompanyRegistryStore) -> list[dict]:
    merged: dict[str, dict] = {}
    with target._connect() as conn:
        for row in conn.execute(
            "SELECT code, symbol, name_fa, market, source_universe FROM listed_companies ORDER BY code"
        ).fetchall():
            merged[row["code"]] = {
                "code": row["code"],
                "symbol": row["symbol"],
                "name": row["name_fa"],
                "market": row["market"],
                "paper_type": None,  # not persisted historically; classification falls back to other signals
                "source": row["source_universe"] or "migration",
            }
    with registry._connect() as conn:
        for row in conn.execute(
            "SELECT code, symbol, name, market, paper_type FROM instrument_registry ORDER BY code"
        ).fetchall():
            # instrument_registry may hold richer data (a live TSETMC fetch's real
            # symbol/name/paper_type) than listed_companies ever captured for this
            # code -- prefer it when both sources know the same code.
            merged[row["code"]] = {
                "code": row["code"],
                "symbol": row["symbol"],
                "name": row["name"],
                "market": row["market"],
                "paper_type": row["paper_type"],
                "source": "instrument-registry-reclassify",
            }
    return [merged[code] for code in sorted(merged)]


def run_migration(db_path: str = DEFAULT_LISTED_COMPANY_DB) -> dict:
    target = ListedCompanyStore(db_path)
    reg = CompanyRegistryStore(db_path)

    run_id = f"migration-{int(time.time())}"
    started_at = _now_iso()
    started_wall = time.time()

    total_unique_companies_before = reg.company_count()
    total_enriched_before = target.status()["enriched"]
    raw_before = target.count()

    raw_rows = _load_raw_rows(target, reg)
    # Wrap plain dicts the same way live query_symbols() items look to _classify_and_register.
    fake_items = [type("Row", (), {"to_dict": (lambda self, d=row: d)})() for row in raw_rows]

    outcome = _classify_and_register(fake_items, target=target, registry=reg, run_id=run_id)

    total_unique_companies_after = reg.company_count()
    total_enriched_after = target.status()["enriched"]
    raw_after = target.count()

    run_row_id = reg.record_run(
        started_at=started_at,
        completed_at=_now_iso(),
        source="migration",
        discovered=len(raw_rows),
        attempted=0,
        succeeded=0,
        failed=0,
        new_unique_companies=outcome["newUniqueCompanies"],
        re_enriched_companies=0,
        newly_classified_instruments=outcome["newlyClassifiedInstruments"],
        excluded_non_company=outcome["excludedNonCompany"],
        unresolved_unknown=outcome["unresolvedUnknown"],
        total_unique_companies_before=total_unique_companies_before,
        total_unique_companies_after=total_unique_companies_after,
        total_enriched_before=total_enriched_before,
        total_enriched_after=total_enriched_after,
        duration_seconds=round(time.time() - started_wall, 3),
        error_summary={},
    )

    assert raw_before == raw_after, "migration must never delete/add listed_companies rows"
    assert total_enriched_before == total_enriched_after, "migration must never touch enriched company_json"

    report = reg.full_report(listed_company_store=target)
    report["runId"] = run_row_id
    report["rawInstrumentsBefore"] = raw_before
    report["rawInstrumentsAfter"] = raw_after
    report["enrichedPreservedCount"] = total_enriched_after
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_LISTED_COMPANY_DB, help="Path to listed_companies.sqlite3")
    args = parser.parse_args()

    report = run_migration(args.db)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    dist = report["classificationDistribution"]
    print("\n--- MIGRATION REPORT ---", file=sys.stderr)
    print(f"RAW INSTRUMENTS: {report['rawInstruments']}", file=sys.stderr)
    print(f"GENUINE UNIQUE COMPANIES: {report['genuineUniqueCompanies']}", file=sys.stderr)
    print(f"ENRICHED UNIQUE COMPANIES: {report['enrichedUniqueCompanies']}", file=sys.stderr)
    print(f"UNENRICHED UNIQUE COMPANIES: {report['unenrichedUniqueCompanies']}", file=sys.stderr)
    print(f"NON-COMPANY INSTRUMENTS: {report['nonCompanyInstruments']}", file=sys.stderr)
    print(f"UNKNOWN/UNRESOLVED: {report['unknownUnresolved']}", file=sys.stderr)
    print(f"DUPLICATE/MULTI-INSTRUMENT MAPPINGS: {report['duplicateMultiInstrumentMappings']}", file=sys.stderr)
    print(f"COVERAGE %: {report['coveragePct']}", file=sys.stderr)
    print(f"CLASSIFICATION DISTRIBUTION: {json.dumps(dist, ensure_ascii=False)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
