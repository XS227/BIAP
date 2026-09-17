"""Persistent instrument classification, issuer registry, and append-only run audit log.

Three tables, additive to the existing ``listed_companies`` schema (same
database file, never dropped/altered):

- ``instrument_registry``: every TSETMC/IFB instrument ever discovered, with
  its classification. Nothing is ever deleted from this table — non-company
  instruments (funds, bonds, options, rights issues, ...) are kept here even
  though they are excluded from the primary company dataset.
- ``company_registry``: one row per genuine, deduplicated issuer/company,
  with a stable ``issuer_id`` derived deterministically from its base symbol.
- ``collection_runs``: append-only audit log, one row per ingestion run. Rows
  are only ever INSERTed; this module exposes no update/delete for this
  table, and it deliberately has no ``updated_at`` column, so historical runs
  can never be overwritten and dataset growth can be reconstructed by date.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import uuid
from typing import Any, Iterable, Optional

from instrument_classifier import COMPANY_CATEGORIES, normalize_text

from listed_company_store import DEFAULT_LISTED_COMPANY_DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def company_id_for(issuer_key: str) -> str:
    """Deterministic, stable issuer id — same issuer_key always maps to the same id."""
    digest = hashlib.sha1(issuer_key.encode("utf-8")).hexdigest()
    return f"co_{digest[:16]}"


class CompanyRegistryStore:
    def __init__(self, db_path: str = DEFAULT_LISTED_COMPANY_DB):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _session(self, conn: Optional[sqlite3.Connection] = None):
        """Reuse a caller-supplied connection (no per-call commit/close, caller
        owns the transaction), or open+commit+close a fresh one as before.

        A bulk classification pass processes thousands of instruments; opening
        a brand-new SQLite connection per row (the original per-method
        ``self._connect()`` pattern) is slow and memory-hungry enough at that
        volume to get the whole process OOM-killed on this host. Passing one
        shared connection through a batch keeps single-call callers unchanged.
        """
        if conn is not None:
            yield conn
        else:
            with self._connect() as owned:
                yield owned

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS instrument_registry (
                    code TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    market TEXT,
                    paper_type TEXT,
                    category TEXT NOT NULL,
                    classification_reason TEXT,
                    issuer_id TEXT,
                    is_duplicate_instrument INTEGER NOT NULL DEFAULT 0,
                    discovered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_run_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_instrument_registry_issuer ON instrument_registry(issuer_id);
                CREATE INDEX IF NOT EXISTS idx_instrument_registry_category ON instrument_registry(category);

                CREATE TABLE IF NOT EXISTS company_registry (
                    issuer_id TEXT PRIMARY KEY,
                    issuer_key TEXT NOT NULL UNIQUE,
                    canonical_symbol TEXT NOT NULL,
                    canonical_name TEXT,
                    category TEXT NOT NULL,
                    primary_instrument_code TEXT NOT NULL,
                    instrument_count INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    first_seen_run_id TEXT,
                    last_seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_company_registry_category ON company_registry(category);

                CREATE TABLE IF NOT EXISTS collection_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    source TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 0,
                    attempted INTEGER NOT NULL DEFAULT 0,
                    succeeded INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    new_unique_companies INTEGER NOT NULL DEFAULT 0,
                    re_enriched_companies INTEGER NOT NULL DEFAULT 0,
                    newly_classified_instruments INTEGER NOT NULL DEFAULT 0,
                    excluded_non_company INTEGER NOT NULL DEFAULT 0,
                    unresolved_unknown INTEGER NOT NULL DEFAULT 0,
                    total_unique_companies_before INTEGER NOT NULL DEFAULT 0,
                    total_unique_companies_after INTEGER NOT NULL DEFAULT 0,
                    total_enriched_before INTEGER NOT NULL DEFAULT 0,
                    total_enriched_after INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL,
                    error_summary TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_collection_runs_started ON collection_runs(started_at);
                """
            )

    # ---- instrument_registry -------------------------------------------------

    def upsert_instrument(
        self,
        *,
        code: str,
        symbol: str,
        name: str | None,
        market: str | None,
        paper_type: str | None,
        category: str,
        reason: str,
        issuer_id: str | None,
        is_duplicate: bool,
        run_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> bool:
        """Insert or refresh one instrument's classification. Returns True if newly discovered."""
        now = _now_iso()
        code = str(code).strip()
        with self._session(conn) as conn:
            existed = conn.execute(
                "SELECT 1 FROM instrument_registry WHERE code=?", (code,)
            ).fetchone() is not None
            conn.execute(
                """
                INSERT INTO instrument_registry
                    (code,symbol,name,market,paper_type,category,classification_reason,issuer_id,
                     is_duplicate_instrument,discovered_at,last_seen_at,last_run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                    symbol=excluded.symbol, name=excluded.name, market=excluded.market,
                    paper_type=excluded.paper_type, category=excluded.category,
                    classification_reason=excluded.classification_reason, issuer_id=excluded.issuer_id,
                    is_duplicate_instrument=excluded.is_duplicate_instrument,
                    last_seen_at=excluded.last_seen_at, last_run_id=excluded.last_run_id
                """,
                (code, symbol, name, market, paper_type, category, reason, issuer_id,
                 1 if is_duplicate else 0, now, now, run_id),
            )
        return not existed

    def get_instrument(self, code: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM instrument_registry WHERE code=?", (str(code).strip(),)).fetchone()
        return dict(row) if row else None

    # ---- company_registry -----------------------------------------------------

    def get_or_create_company(
        self,
        *,
        issuer_key_value: str,
        symbol: str,
        name: str | None,
        category: str,
        primary_instrument_code: str,
        run_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> tuple[str, bool]:
        """Return (issuer_id, created). Never renames/loses an existing company on re-run."""
        issuer_id = company_id_for(issuer_key_value)
        now = _now_iso()
        with self._session(conn) as conn:
            existing = conn.execute(
                "SELECT issuer_id FROM company_registry WHERE issuer_id=?", (issuer_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE company_registry SET last_seen_at=? WHERE issuer_id=?",
                    (now, issuer_id),
                )
                return issuer_id, False
            conn.execute(
                """
                INSERT INTO company_registry
                    (issuer_id,issuer_key,canonical_symbol,canonical_name,category,
                     primary_instrument_code,instrument_count,first_seen_at,first_seen_run_id,last_seen_at)
                VALUES (?,?,?,?,?,?,1,?,?,?)
                """,
                (issuer_id, issuer_key_value, normalize_text(symbol), normalize_text(name) or None,
                 category, primary_instrument_code, now, run_id, now),
            )
            return issuer_id, True

    def bump_instrument_count(self, issuer_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE company_registry SET instrument_count = instrument_count + 1, last_seen_at=? WHERE issuer_id=?",
                (_now_iso(), issuer_id),
            )

    def company_exists(self, issuer_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        with self._session(conn) as conn:
            return conn.execute(
                "SELECT 1 FROM company_registry WHERE issuer_id=?", (issuer_id,)
            ).fetchone() is not None

    def prune_orphaned_companies(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Remove company_registry rows no longer backed by any company-category instrument.

        Classification can improve over time (better keyword coverage, new
        verification signals): an issuer that was previously misclassified as
        a genuine company (e.g. a rights issue whose name keyword-matched a
        financial-company bucket before rights detection covered its naming
        pattern) may later have every one of its instruments correctly
        reclassified. When that happens, its registry row would otherwise sit
        forever as a stale, uncorrectable entry -- unlike ``collection_runs``,
        company_registry is a derived, self-healing view of current
        classification truth, not an audit trail, so pruning it is safe and
        never touches ``listed_companies``/``company_json``.
        """
        with self._session(conn) as conn:
            placeholders = ",".join("?" for _ in COMPANY_CATEGORIES)
            cur = conn.execute(
                f"""
                DELETE FROM company_registry
                WHERE issuer_id NOT IN (
                    SELECT DISTINCT issuer_id FROM instrument_registry
                    WHERE issuer_id IS NOT NULL AND category IN ({placeholders})
                )
                """,
                tuple(COMPANY_CATEGORIES),
            )
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def company_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM company_registry").fetchone()[0])

    def primary_company_codes(self) -> list[str]:
        """Instrument codes eligible for enrichment: one per genuine company."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT primary_instrument_code FROM company_registry "
                f"WHERE category IN ({','.join('?' for _ in COMPANY_CATEGORIES)}) "
                f"ORDER BY primary_instrument_code",
                tuple(COMPANY_CATEGORIES),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def classification_distribution(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) c FROM instrument_registry GROUP BY category"
            ).fetchall()
        return {str(row["category"]): int(row["c"]) for row in rows}

    def duplicate_mapping_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM instrument_registry WHERE is_duplicate_instrument=1"
            ).fetchone()[0])

    def raw_instrument_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM instrument_registry").fetchone()[0])

    def instruments_for_issuer(self, issuer_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM instrument_registry WHERE issuer_id=? ORDER BY code", (issuer_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- collection_runs (append-only) -----------------------------------------

    def record_run(
        self,
        *,
        started_at: str,
        completed_at: str | None,
        source: str,
        discovered: int,
        attempted: int,
        succeeded: int,
        failed: int,
        new_unique_companies: int,
        re_enriched_companies: int,
        newly_classified_instruments: int,
        excluded_non_company: int,
        unresolved_unknown: int,
        total_unique_companies_before: int,
        total_unique_companies_after: int,
        total_enriched_before: int,
        total_enriched_after: int,
        duration_seconds: float | None,
        error_summary: dict[str, Any] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO collection_runs
                    (run_id,started_at,completed_at,source,discovered,attempted,succeeded,failed,
                     new_unique_companies,re_enriched_companies,newly_classified_instruments,
                     excluded_non_company,unresolved_unknown,total_unique_companies_before,
                     total_unique_companies_after,total_enriched_before,total_enriched_after,
                     duration_seconds,error_summary,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (run_id, started_at, completed_at, source, discovered, attempted, succeeded, failed,
                 new_unique_companies, re_enriched_companies, newly_classified_instruments,
                 excluded_non_company, unresolved_unknown, total_unique_companies_before,
                 total_unique_companies_after, total_enriched_before, total_enriched_after,
                 duration_seconds, json.dumps(error_summary or {}, ensure_ascii=False, sort_keys=True),
                 _now_iso()),
            )
        return run_id

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 1000)),)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["error_summary"] = json.loads(item.get("error_summary") or "{}")
            except (TypeError, ValueError):
                pass
            result.append(item)
        return result

    def growth_by_date(self) -> list[dict[str, Any]]:
        """Reconstruct how the company dataset grew by date, from the immutable run log."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(started_at,1,10) AS day,
                       SUM(new_unique_companies) AS new_companies,
                       SUM(re_enriched_companies) AS re_enrichments,
                       COUNT(*) AS runs
                FROM collection_runs GROUP BY day ORDER BY day
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def full_report(self, *, listed_company_store) -> dict[str, Any]:
        """Everything required by the reporting spec, in one call."""
        raw_total = self.raw_instrument_count()
        companies_total = self.company_count()
        classification = self.classification_distribution()
        primary_codes = self.primary_company_codes()
        enriched_status = listed_company_store.status()
        enriched_primary = 0
        if primary_codes:
            placeholders = ",".join("?" for _ in primary_codes)
            with listed_company_store._connect() as conn:  # same physical db file
                enriched_primary = int(conn.execute(
                    f"SELECT COUNT(*) FROM listed_companies WHERE code IN ({placeholders}) AND company_json IS NOT NULL",
                    primary_codes,
                ).fetchone()[0])
        non_company_categories = {
            cat: count for cat, count in classification.items() if cat not in COMPANY_CATEGORIES
        }
        return {
            "rawInstruments": raw_total,
            "genuineUniqueCompanies": companies_total,
            "enrichedUniqueCompanies": enriched_primary,
            "unenrichedUniqueCompanies": max(0, len(primary_codes) - enriched_primary),
            "nonCompanyInstruments": sum(
                count for cat, count in non_company_categories.items()
                if cat != "duplicate_share_class"
            ),
            "unknownUnresolved": classification.get("unknown", 0),
            "duplicateMultiInstrumentMappings": self.duplicate_mapping_count(),
            "coveragePct": round((enriched_primary / len(primary_codes) * 100.0), 2) if primary_codes else 0.0,
            "classificationDistribution": classification,
            "enrichedStatusLegacy": enriched_status,
            "growthByDate": self.growth_by_date(),
        }
