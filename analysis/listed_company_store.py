"""Persistent indexed store for BIAP listed-company records and ingestion state."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Iterable, Optional

DEFAULT_LISTED_COMPANY_DB = os.environ.get(
    "BIAP_LISTED_COMPANY_DB",
    os.path.join(os.path.dirname(__file__), "listed_companies.sqlite3"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: str | None) -> str:
    return " ".join((value or "").translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u200c": "", "\u200f": "", "\u200e": ""})).split()).strip()


class ListedCompanyStore:
    def __init__(self, db_path: str = DEFAULT_LISTED_COMPANY_DB):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listed_companies (
                    code TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name_fa TEXT,
                    market TEXT,
                    source_universe TEXT,
                    source_updated_at TEXT,
                    enriched_at TEXT,
                    company_json TEXT,
                    provenance_json TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_listed_companies_symbol ON listed_companies(symbol);
                CREATE INDEX IF NOT EXISTS idx_listed_companies_name ON listed_companies(name_fa);
                CREATE INDEX IF NOT EXISTS idx_listed_companies_market ON listed_companies(market);
                CREATE INDEX IF NOT EXISTS idx_listed_companies_updated ON listed_companies(updated_at);

                CREATE TABLE IF NOT EXISTS listed_company_ingestion_state (
                    worker TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    cursor INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    processed INTEGER NOT NULL DEFAULT 0,
                    succeeded INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    last_code TEXT,
                    last_error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def upsert_universe(self, items: Iterable[Any]) -> int:
        now = _now_iso()
        rows = []
        for item in items:
            data = item.to_dict() if hasattr(item, "to_dict") else dict(item)
            code = _normalize(str(data.get("code") or data.get("instrumentCode") or data.get("ticker") or ""))
            symbol = _normalize(str(data.get("symbol") or data.get("name") or code))
            if not code:
                continue
            rows.append((
                code,
                symbol or code,
                _normalize(data.get("name") or data.get("name_fa") or symbol) or None,
                _normalize(data.get("market")) or None,
                str(data.get("source") or "unknown"),
                str(data.get("fetchedAt") or data.get("updatedAt") or now),
                json.dumps({"universe": {"source": data.get("source"), "observedAt": data.get("fetchedAt") or data.get("updatedAt") or now}}, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ))
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO listed_companies
                    (code,symbol,name_fa,market,source_universe,source_updated_at,provenance_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                    symbol=excluded.symbol,
                    name_fa=COALESCE(excluded.name_fa,listed_companies.name_fa),
                    market=COALESCE(excluded.market,listed_companies.market),
                    source_universe=excluded.source_universe,
                    source_updated_at=excluded.source_updated_at,
                    provenance_json=excluded.provenance_json,
                    updated_at=excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def save_enriched(self, code: str, company: dict[str, Any], *, provenance: dict[str, Any], error: str | None = None) -> None:
        now = _now_iso()
        canonical = _normalize(code).upper()
        symbol = _normalize(str(company.get("ticker") or canonical)) or canonical
        name = _normalize(company.get("name_fa") or symbol) or None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO listed_companies
                    (code,symbol,name_fa,market,source_universe,source_updated_at,enriched_at,company_json,provenance_json,last_error,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                    symbol=excluded.symbol,
                    name_fa=COALESCE(excluded.name_fa,listed_companies.name_fa),
                    enriched_at=excluded.enriched_at,
                    company_json=excluded.company_json,
                    provenance_json=excluded.provenance_json,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (canonical, symbol, name, None, "company_builder", now, now,
                 json.dumps(company, ensure_ascii=False, sort_keys=True),
                 json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                 error, now, now),
            )

    def record_error(self, code: str, error: str) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute("UPDATE listed_companies SET last_error=?,updated_at=? WHERE code=?", (error[:1000], now, _normalize(code).upper()))

    @staticmethod
    def _row(row: sqlite3.Row, *, include_company: bool) -> dict[str, Any]:
        result = {
            "code": row["code"], "symbol": row["symbol"], "name": row["name_fa"], "market": row["market"],
            "sourceUniverse": row["source_universe"], "sourceUpdatedAt": row["source_updated_at"],
            "enrichedAt": row["enriched_at"], "provenance": json.loads(row["provenance_json"] or "{}"),
            "lastError": row["last_error"], "updatedAt": row["updated_at"],
        }
        if include_company:
            result["company"] = json.loads(row["company_json"]) if row["company_json"] else None
        return result

    def get(self, code: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM listed_companies WHERE code=? OR symbol=? LIMIT 1", (_normalize(code).upper(), _normalize(code))).fetchone()
        return self._row(row, include_company=True) if row else None

    def search(self, q: str | None = None, *, market: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        wanted = _normalize(q)
        if wanted:
            clauses.append("(code LIKE ? OR symbol LIKE ? OR name_fa LIKE ?)")
            like = f"%{wanted}%"
            args.extend((like, like, like))
        if market:
            clauses.append("UPPER(market)=?")
            args.append(market.upper())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        args.extend((max(1, min(int(limit), 1000)), max(0, int(offset))))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM listed_companies{where} ORDER BY symbol COLLATE NOCASE LIMIT ? OFFSET ?", args).fetchall()
        return [self._row(row, include_company=False) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM listed_companies").fetchone()[0])

    def pending_codes(self, *, start: int = 0, limit: int = 100) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT code FROM listed_companies ORDER BY code LIMIT ? OFFSET ?", (max(1, min(limit, 5000)), max(0, start))).fetchall()
        return [str(row["code"]) for row in rows]

    def save_state(self, worker: str, *, status: str, cursor: int, total: int, processed: int, succeeded: int, failed: int, started_at: str | None, completed_at: str | None = None, last_code: str | None = None, last_error: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO listed_company_ingestion_state
                    (worker,status,cursor,total,processed,succeeded,failed,started_at,updated_at,completed_at,last_code,last_error,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(worker) DO UPDATE SET
                    status=excluded.status,cursor=excluded.cursor,total=excluded.total,processed=excluded.processed,
                    succeeded=excluded.succeeded,failed=excluded.failed,started_at=excluded.started_at,updated_at=excluded.updated_at,
                    completed_at=excluded.completed_at,last_code=excluded.last_code,last_error=excluded.last_error,metadata_json=excluded.metadata_json
                """,
                (worker,status,cursor,total,processed,succeeded,failed,started_at,now,completed_at,last_code,last_error,
                 json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)),
            )
        return self.get_state(worker) or {}

    def get_state(self, worker: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM listed_company_ingestion_state WHERE worker=?", (worker,)).fetchone()
        if row is None:
            return None
        return {
            "worker": row["worker"], "status": row["status"], "cursor": int(row["cursor"]), "total": int(row["total"]),
            "processed": int(row["processed"]), "succeeded": int(row["succeeded"]), "failed": int(row["failed"]),
            "startedAt": row["started_at"], "updatedAt": row["updated_at"], "completedAt": row["completed_at"],
            "lastCode": row["last_code"], "lastError": row["last_error"], "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) total, SUM(CASE WHEN company_json IS NOT NULL THEN 1 ELSE 0 END) enriched, SUM(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) errors, MAX(updated_at) latest FROM listed_companies").fetchone()
            workers = conn.execute("SELECT worker FROM listed_company_ingestion_state ORDER BY worker").fetchall()
        return {
            "total": int(row["total"] or 0), "enriched": int(row["enriched"] or 0), "errors": int(row["errors"] or 0),
            "updatedAt": row["latest"], "workers": [self.get_state(str(worker["worker"])) for worker in workers],
        }
