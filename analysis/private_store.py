"""Private, per-user operational data: CRM contacts/leads/activities and the KPI register.

Strictly separate from listed-company public data: nothing here is ever generated or inferred, every
row was entered (or imported) by the authorized user and is isolated by ``user_id``.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = os.getenv("BIAP_PRIVATE_OPS_DB", "/var/lib/biap/private_ops.sqlite3")
STAGES = ["lead", "qualified", "proposal", "negotiation", "won", "lost"]
DEFAULT_PROBABILITY = {"lead": 0.1, "qualified": 0.25, "proposal": 0.5, "negotiation": 0.75, "won": 1.0, "lost": 0.0}
ACTIVITY_TYPES = ["call", "meeting", "email", "note", "task"]
_lock = threading.Lock()


class PrivateDataError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Optional[str] = None) -> sqlite3.Connection:
    p = path or DB_PATH
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crm_contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL,
            company TEXT, email TEXT, phone TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_contacts_user ON crm_contacts(user_id);
        CREATE TABLE IF NOT EXISTS crm_leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, contact_id INTEGER,
            title TEXT NOT NULL, stage TEXT NOT NULL, value REAL, currency TEXT, next_step TEXT, due_date TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(contact_id) REFERENCES crm_contacts(id) ON DELETE SET NULL);
        CREATE INDEX IF NOT EXISTS ix_leads_user ON crm_leads(user_id, stage);
        CREATE TABLE IF NOT EXISTS crm_activities (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, lead_id INTEGER,
            contact_id INTEGER, type TEXT NOT NULL, summary TEXT NOT NULL, occurred_at TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_acts_user ON crm_activities(user_id, occurred_at);
        CREATE TABLE IF NOT EXISTS kpi_register (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL,
            owner TEXT, target REAL, unit TEXT, cadence TEXT, current_value REAL, updated_at TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_kpi_user ON kpi_register(user_id);
    """)
    return conn


def _txt(v: Any, name: str, *, required: bool = False, max_len: int = 500) -> Optional[str]:
    if v is None or str(v).strip() == "":
        if required:
            raise PrivateDataError(f"{name} is required")
        return None
    s = str(v).strip()
    if len(s) > max_len:
        raise PrivateDataError(f"{name} is too long")
    return s


def _numf(v: Any, name: str) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise PrivateDataError(f"{name} must be a number")
    if f != f or f in (float("inf"), float("-inf")):
        raise PrivateDataError(f"{name} must be finite")
    return f


class PrivateStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path

    def _c(self) -> sqlite3.Connection:
        return _connect(self.path)

    # contacts
    def add_contact(self, user_id: str, data: dict) -> dict:
        row = (user_id, _txt(data.get("name"), "name", required=True, max_len=120), _txt(data.get("company"), "company", max_len=160),
               _txt(data.get("email"), "email", max_len=160), _txt(data.get("phone"), "phone", max_len=40), _txt(data.get("notes"), "notes", max_len=2000), _now(), _now())
        with _lock, self._c() as c:
            cur = c.execute("INSERT INTO crm_contacts (user_id,name,company,email,phone,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", row)
            return self.get_contact(user_id, cur.lastrowid, conn=c)

    def get_contact(self, user_id: str, cid: int, conn=None) -> dict:
        c = conn or self._c()
        r = c.execute("SELECT * FROM crm_contacts WHERE id=? AND user_id=?", (cid, user_id)).fetchone()
        if not r:
            raise PrivateDataError("contact not found")
        return dict(r)

    def list_contacts(self, user_id: str, q: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
        sql, args = "SELECT * FROM crm_contacts WHERE user_id=?", [user_id]
        if q:
            sql += " AND (name LIKE ? OR company LIKE ? OR email LIKE ?)"
            args += [f"%{q}%"] * 3
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        args += [max(1, min(limit, 500)), max(0, offset)]
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def update_contact(self, user_id: str, cid: int, data: dict) -> dict:
        cur = self.get_contact(user_id, cid)
        merged = {**cur, **{k: v for k, v in data.items() if k in ("name", "company", "email", "phone", "notes")}}
        with _lock, self._c() as c:
            c.execute("UPDATE crm_contacts SET name=?,company=?,email=?,phone=?,notes=?,updated_at=? WHERE id=? AND user_id=?",
                      (_txt(merged["name"], "name", required=True), _txt(merged.get("company"), "company"), _txt(merged.get("email"), "email"),
                       _txt(merged.get("phone"), "phone"), _txt(merged.get("notes"), "notes", max_len=2000), _now(), cid, user_id))
        return self.get_contact(user_id, cid)

    def delete_contact(self, user_id: str, cid: int) -> None:
        with _lock, self._c() as c:
            c.execute("DELETE FROM crm_contacts WHERE id=? AND user_id=?", (cid, user_id))

    # leads
    def add_lead(self, user_id: str, data: dict) -> dict:
        stage = str(data.get("stage") or "lead")
        if stage not in STAGES:
            raise PrivateDataError(f"stage must be one of {STAGES}")
        cid = data.get("contactId")
        if cid is not None:
            self.get_contact(user_id, int(cid))
        with _lock, self._c() as c:
            cur = c.execute("INSERT INTO crm_leads (user_id,contact_id,title,stage,value,currency,next_step,due_date,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (user_id, cid, _txt(data.get("title"), "title", required=True, max_len=200), stage, _numf(data.get("value"), "value"),
                             _txt(data.get("currency"), "currency", max_len=8), _txt(data.get("nextStep"), "nextStep"), _txt(data.get("dueDate"), "dueDate", max_len=32), _now(), _now()))
            return self.get_lead(user_id, cur.lastrowid, conn=c)

    def get_lead(self, user_id: str, lid: int, conn=None) -> dict:
        c = conn or self._c()
        r = c.execute("SELECT * FROM crm_leads WHERE id=? AND user_id=?", (lid, user_id)).fetchone()
        if not r:
            raise PrivateDataError("lead not found")
        return dict(r)

    def list_leads(self, user_id: str, stage: Optional[str] = None, limit: int = 200, offset: int = 0) -> list[dict]:
        sql, args = "SELECT * FROM crm_leads WHERE user_id=?", [user_id]
        if stage:
            sql += " AND stage=?"
            args.append(stage)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        args += [max(1, min(limit, 500)), max(0, offset)]
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def move_lead(self, user_id: str, lid: int, data: dict) -> dict:
        cur = self.get_lead(user_id, lid)
        stage = data.get("stage", cur["stage"])
        if stage not in STAGES:
            raise PrivateDataError(f"stage must be one of {STAGES}")
        with _lock, self._c() as c:
            c.execute("UPDATE crm_leads SET stage=?,value=?,next_step=?,due_date=?,title=?,updated_at=? WHERE id=? AND user_id=?",
                      (stage, _numf(data.get("value", cur["value"]), "value"), _txt(data.get("nextStep", cur["next_step"]), "nextStep"),
                       _txt(data.get("dueDate", cur["due_date"]), "dueDate", max_len=32), _txt(data.get("title", cur["title"]), "title", required=True, max_len=200), _now(), lid, user_id))
        return self.get_lead(user_id, lid)

    def delete_lead(self, user_id: str, lid: int) -> None:
        with _lock, self._c() as c:
            c.execute("DELETE FROM crm_leads WHERE id=? AND user_id=?", (lid, user_id))

    # activities
    def add_activity(self, user_id: str, data: dict) -> dict:
        typ = str(data.get("type") or "note")
        if typ not in ACTIVITY_TYPES:
            raise PrivateDataError(f"type must be one of {ACTIVITY_TYPES}")
        if data.get("leadId") is not None:
            self.get_lead(user_id, int(data["leadId"]))
        if data.get("contactId") is not None:
            self.get_contact(user_id, int(data["contactId"]))
        with _lock, self._c() as c:
            cur = c.execute("INSERT INTO crm_activities (user_id,lead_id,contact_id,type,summary,occurred_at,created_at) VALUES (?,?,?,?,?,?,?)",
                            (user_id, data.get("leadId"), data.get("contactId"), typ, _txt(data.get("summary"), "summary", required=True, max_len=1000),
                             _txt(data.get("occurredAt"), "occurredAt", max_len=40) or _now(), _now()))
            return dict(c.execute("SELECT * FROM crm_activities WHERE id=?", (cur.lastrowid,)).fetchone())

    def list_activities(self, user_id: str, lead_id: Optional[int] = None, limit: int = 100) -> list[dict]:
        sql, args = "SELECT * FROM crm_activities WHERE user_id=?", [user_id]
        if lead_id is not None:
            sql += " AND lead_id=?"
            args.append(lead_id)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def pipeline(self, user_id: str, probability: Optional[dict] = None) -> dict:
        prob = {**DEFAULT_PROBABILITY, **{k: float(v) for k, v in (probability or {}).items() if k in STAGES}}
        with self._c() as c:
            rows = c.execute("SELECT stage, COUNT(*) n, COALESCE(SUM(value),0) total, SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) novalue FROM crm_leads WHERE user_id=? GROUP BY stage", (user_id,)).fetchall()
            contacts = c.execute("SELECT COUNT(*) FROM crm_contacts WHERE user_id=?", (user_id,)).fetchone()[0]
            acts = c.execute("SELECT COUNT(*) FROM crm_activities WHERE user_id=?", (user_id,)).fetchone()[0]
        by = {r["stage"]: dict(r) for r in rows}
        stages = [{"stage": s, "count": by.get(s, {}).get("n", 0), "value": by.get(s, {}).get("total", 0.0), "probability": prob[s],
                   "weighted": by.get(s, {}).get("total", 0.0) * prob[s]} for s in STAGES]
        closed = by.get("won", {}).get("n", 0) + by.get("lost", {}).get("n", 0)
        return {"stages": stages, "contacts": contacts, "activities": acts, "leads": sum(s["count"] for s in stages),
                "winRate": (by.get("won", {}).get("n", 0) / closed) if closed else None,
                "weightedValue": sum(s["weighted"] for s in stages if s["stage"] not in ("won", "lost")),
                "probabilityNote": "احتمال هر مرحله فرض قابل ویرایش شماست، نه داده‌ی مشاهده‌شده."}

    # KPI register
    def upsert_kpi(self, user_id: str, data: dict, kid: Optional[int] = None) -> dict:
        vals = (_txt(data.get("name"), "name", required=True, max_len=160), _txt(data.get("owner"), "owner", max_len=120), _numf(data.get("target"), "target"),
                _txt(data.get("unit"), "unit", max_len=20), _txt(data.get("cadence"), "cadence", max_len=40), _numf(data.get("currentValue"), "currentValue"))
        with _lock, self._c() as c:
            if kid is None:
                cur = c.execute("INSERT INTO kpi_register (user_id,name,owner,target,unit,cadence,current_value,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user_id, *vals, _now(), _now()))
                kid = cur.lastrowid
            else:
                if not c.execute("SELECT 1 FROM kpi_register WHERE id=? AND user_id=?", (kid, user_id)).fetchone():
                    raise PrivateDataError("kpi not found")
                c.execute("UPDATE kpi_register SET name=?,owner=?,target=?,unit=?,cadence=?,current_value=?,updated_at=? WHERE id=? AND user_id=?", (*vals, _now(), kid, user_id))
            return dict(c.execute("SELECT * FROM kpi_register WHERE id=?", (kid,)).fetchone())

    def list_kpis(self, user_id: str) -> list[dict]:
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM kpi_register WHERE user_id=? ORDER BY name", (user_id,))]

    def delete_kpi(self, user_id: str, kid: int) -> None:
        with _lock, self._c() as c:
            c.execute("DELETE FROM kpi_register WHERE id=? AND user_id=?", (kid, user_id))
