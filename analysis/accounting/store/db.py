"""Accounting store with per-company isolation.

Rules enforced here (owner conditions, 2026-11-02):
  * separate SQLite file, never shared with other modules;
  * every call names a user, and a user only reaches companies they are a member of;
  * nothing about accounts, amounts or descriptions is ever logged: log lines carry
    only operation names, numeric ids and counts.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, Optional

log = logging.getLogger("biap.accounting")

SCHEMA_VERSION = "1"
WRITE_ROLES = {"owner", "accountant"}


class StoreError(Exception):
    """Invalid input. Messages never contain accounting values."""


class AccessDenied(StoreError):
    """User is not a member of the company (or lacks the role)."""


def to_ore(value) -> int:
    """'1234.56' / Decimal / int NOK -> integer ore. Rejects more than 2 decimals."""
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise StoreError("invalid amount") from exc
    ore = d * 100
    if ore != ore.to_integral_value():
        raise StoreError("amount has more than 2 decimals")
    return int(ore)


def from_ore(ore: int) -> Decimal:
    return (Decimal(ore) / 100).quantize(Decimal("0.01"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AccountingStore:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        if new:
            os.chmod(self.path, 0o600)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        sql = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
        self._conn.executescript(sql)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # ---- access control -------------------------------------------------
    def _require(self, user_id: str, company_id: int, write: bool = False) -> str:
        row = self._conn.execute(
            "SELECT role FROM company_users WHERE company_id=? AND user_id=?",
            (company_id, user_id)).fetchone()
        if row is None:
            # Same error whether the company exists or not: no existence oracle.
            raise AccessDenied("no access to this company")
        if write and row["role"] not in WRITE_ROLES:
            raise AccessDenied("read-only role")
        return row["role"]

    # ---- companies ------------------------------------------------------
    def create_company(self, user_id: str, org_number: str, name: str, *, is_test: bool = False) -> int:
        if not user_id or not org_number or not name:
            raise StoreError("user, org number and name are required")
        try:
            with self._tx() as c:
                cur = c.execute(
                    "INSERT INTO companies(org_number,name,is_test,created_at) VALUES(?,?,?,?)",
                    (org_number, name, int(is_test), _now()))
                cid = cur.lastrowid
                c.execute("INSERT INTO company_users VALUES(?,?,'owner')", (cid, user_id))
        except sqlite3.IntegrityError as exc:
            raise StoreError("company already exists") from exc
        log.info("company created id=%s", cid)
        return cid

    def list_companies(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT c.id, c.org_number, c.name, c.is_test, u.role FROM companies c "
            "JOIN company_users u ON u.company_id=c.id WHERE u.user_id=? ORDER BY c.id", (user_id,))
        return [dict(r) for r in rows]

    def add_member(self, owner_id: str, company_id: int, user_id: str, role: str) -> None:
        if self._require(owner_id, company_id) != "owner":
            raise AccessDenied("only the owner manages members")
        with self._tx() as c:
            c.execute("INSERT OR REPLACE INTO company_users VALUES(?,?,?)", (company_id, user_id, role))
        log.info("member set company=%s", company_id)

    # ---- chart of accounts ---------------------------------------------
    def upsert_accounts(self, user_id: str, company_id: int, accounts: Iterable[dict]) -> int:
        self._require(user_id, company_id, write=True)
        n = 0
        with self._tx() as c:
            for a in accounts:
                for k in ("account_id", "description", "grouping_category", "grouping_code"):
                    if not a.get(k):
                        raise StoreError(f"account field missing: {k}")
                c.execute(
                    "INSERT INTO accounts VALUES(?,?,?,?,?,?) ON CONFLICT(company_id,account_id) DO UPDATE SET "
                    "description=excluded.description, grouping_category=excluded.grouping_category, "
                    "grouping_code=excluded.grouping_code, opening_ore=excluded.opening_ore",
                    (company_id, a["account_id"], a["description"], a["grouping_category"],
                     a["grouping_code"], to_ore(a.get("opening", 0))))
                n += 1
        log.info("accounts upserted company=%s count=%s", company_id, n)
        return n

    def upsert_tax_codes(self, user_id: str, company_id: int, codes: Iterable[dict]) -> int:
        self._require(user_id, company_id, write=True)
        n = 0
        with self._tx() as c:
            for t in codes:
                try:
                    c.execute(
                        "INSERT INTO tax_codes VALUES(?,?,?,?) ON CONFLICT(company_id,tax_code) DO UPDATE SET "
                        "description=excluded.description, standard_tax_code=excluded.standard_tax_code",
                        (company_id, t["tax_code"], t["description"], t.get("standard_tax_code") or "NA"))
                except (KeyError, sqlite3.IntegrityError) as exc:
                    raise StoreError("invalid tax code row") from exc
                n += 1
        log.info("tax codes upserted company=%s count=%s", company_id, n)
        return n

    def list_accounts(self, user_id: str, company_id: int) -> list[dict]:
        self._require(user_id, company_id)
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM accounts WHERE company_id=? ORDER BY account_id", (company_id,))]

    # ---- journal --------------------------------------------------------
    def post_entry(self, user_id: str, company_id: int, entry: dict, *, source: str = "manual") -> int:
        """Post one balanced transaction. entry['lines'][i]: account_id, description,
        and exactly one of debit/credit (NOK, max 2 decimals)."""
        self._require(user_id, company_id, write=True)
        if source not in ("manual", "file"):
            raise StoreError("invalid source")
        lines = entry.get("lines") or []
        if len(lines) < 2:
            raise StoreError("an entry needs at least two lines")
        amounts = []
        for ln in lines:
            d, cr = ln.get("debit"), ln.get("credit")
            if (d is None) == (cr is None):
                raise StoreError("each line needs exactly one of debit or credit")
            ore = to_ore(d) if d is not None else -to_ore(cr)
            if ore <= 0 and d is not None or ore >= 0 and cr is not None:
                raise StoreError("amounts must be positive")
            amounts.append(ore)
        if sum(amounts) != 0:
            raise StoreError("entry does not balance")
        for k in ("transaction_id", "period", "period_year", "transaction_date", "description",
                  "system_entry_date", "gl_posting_date"):
            if not entry.get(k):
                raise StoreError(f"entry field missing: {k}")
        try:
            with self._tx() as c:
                eid = (c.execute("SELECT COALESCE(MAX(id),0)+1 FROM entries WHERE company_id=?",
                                 (company_id,)).fetchone()[0])
                c.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (company_id, eid, entry["transaction_id"], entry["period"], entry["period_year"],
                           entry["transaction_date"], entry["description"], entry["system_entry_date"],
                           entry["gl_posting_date"], source))
                for i, (ln, ore) in enumerate(zip(lines, amounts), 1):
                    c.execute("INSERT INTO lines VALUES(?,?,?,?,?,?,?)",
                              (company_id, eid, str(ln.get("record_id") or i), ln["account_id"],
                               ln.get("description") or entry["description"], ore, ln.get("tax_code")))
        except sqlite3.IntegrityError as exc:
            # Do not echo the driver message: it can contain values.
            raise StoreError("entry rejected (duplicate id or unknown account/tax code)") from exc
        log.info("entry posted company=%s id=%s lines=%s", company_id, eid, len(lines))
        return eid

    def list_entries(self, user_id: str, company_id: int, period_year: Optional[str] = None) -> list[dict]:
        self._require(user_id, company_id)
        q = "SELECT * FROM entries WHERE company_id=?"
        args: list = [company_id]
        if period_year:
            q += " AND period_year=?"
            args.append(period_year)
        out = []
        for e in self._conn.execute(q + " ORDER BY id", args):
            d = dict(e)
            d["lines"] = [dict(r) for r in self._conn.execute(
                "SELECT * FROM lines WHERE company_id=? AND entry_id=? ORDER BY rowid", (company_id, e["id"]))]
            out.append(d)
        return out

    def trial_balance(self, user_id: str, company_id: int) -> dict[str, int]:
        self._require(user_id, company_id)
        return {r["account_id"]: r["s"] for r in self._conn.execute(
            "SELECT account_id, SUM(amount_ore) s FROM lines WHERE company_id=? GROUP BY account_id",
            (company_id,))}
