"""Make ``listed_companies`` cover every primary company of ``company_registry`` (insert-only, idempotent).

The registry is the canonical discovery source. A primary company that has no stored row (matched on the
spelling-folded code, so ZWNJ / Arabic-letter variants are NOT duplicated) gets an identity-only row; the
nightly enrichment then fills market and CODAL data. Existing rows - including verified reports - are never
modified.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from codal_inbox import symbol_key
from listed_company_store import ListedCompanyStore


def missing_primary_rows(store: ListedCompanyStore) -> list[dict[str, Any]]:
    from company_registry_store import COMPANY_CATEGORIES
    marks = ",".join("?" for _ in COMPANY_CATEGORIES)
    with closing(sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            companies = conn.execute(
                f"SELECT c.primary_instrument_code code, c.canonical_symbol symbol, c.canonical_name name, i.market market "
                f"FROM company_registry c LEFT JOIN instrument_registry i ON i.code=c.primary_instrument_code WHERE c.category IN ({marks})",
                tuple(COMPANY_CATEGORIES)).fetchall()
        except sqlite3.Error:
            return []
        stored = {symbol_key(r[0]) for r in conn.execute("SELECT code FROM listed_companies")}
    return [dict(c) for c in companies if symbol_key(c["code"]) not in stored]


def reconcile(store: ListedCompanyStore, *, dry_run: bool = False) -> dict[str, Any]:
    missing = missing_primary_rows(store)
    added = 0
    if missing and not dry_run:
        added = store.upsert_universe([{"code": m["code"], "symbol": m["symbol"], "name": m["name"] or m["symbol"],
                                         "market": m["market"], "source": "company_registry"} for m in missing])
    return {"missing": len(missing), "added": added, "dryRun": dry_run, "sample": [m["symbol"] for m in missing[:5]]}


if __name__ == "__main__":  # python registry_reconcile.py [--apply]
    import json
    import sys
    print(json.dumps(reconcile(ListedCompanyStore(), dry_run="--apply" not in sys.argv), ensure_ascii=False))
