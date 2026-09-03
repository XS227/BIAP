"""Kiasha capital mandates and isolated accounting.

Paper mandates are implemented today. The aggregate profile deliberately keeps
PAPER and REAL capital in separate buckets so simulated money can never be
presented as real client assets. A future licensed broker integration may add
REAL mandates through the same accounting contract only after verified custody
and fills exist.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Literal, Optional
from uuid import uuid4
from audit_store import DEFAULT_DB_PATH

Horizon = Literal["week", "month"]

def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(value: datetime) -> str: return value.astimezone(timezone.utc).isoformat()
def _duration_days(horizon: str) -> int:
    if horizon == "week": return 7
    if horizon == "month": return 30
    raise ValueError("horizon must be week or month")

class KiashaCapitalMandateStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH): self.db_path=db_path; self._init_db()
    def _connect(self):
        conn=sqlite3.connect(self.db_path, timeout=30); conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA foreign_keys=ON"); return conn
    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS kiasha_capital_mandates (
              mandate_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,allocated_cash REAL NOT NULL CHECK(allocated_cash>0),
              mandate_cash REAL NOT NULL CHECK(mandate_cash>=0),horizon TEXT NOT NULL CHECK(horizon IN('week','month')),
              status TEXT NOT NULL CHECK(status IN('ACTIVE','STOPPING','COMPLETED')),starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,
              stop_requested_at TEXT,completed_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_user_status ON kiasha_capital_mandates(user_id,status,created_at);
            CREATE TABLE IF NOT EXISTS kiasha_mandate_positions (
              mandate_id TEXT NOT NULL,code TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>=0),avg_cost REAL NOT NULL CHECK(avg_cost>=0),
              realized_pnl REAL NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(mandate_id,code),
              FOREIGN KEY(mandate_id) REFERENCES kiasha_capital_mandates(mandate_id));
            CREATE TABLE IF NOT EXISTS kiasha_mandate_fills (
              fill_id TEXT PRIMARY KEY,mandate_id TEXT NOT NULL,user_id TEXT NOT NULL,intent_id TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN('BUY','SELL')),
              code TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),price REAL NOT NULL CHECK(price>0),notional REAL NOT NULL CHECK(notional>0),
              realized_pnl REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(user_id,intent_id),
              FOREIGN KEY(mandate_id) REFERENCES kiasha_capital_mandates(mandate_id));
            CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_fills_mandate ON kiasha_mandate_fills(mandate_id,created_at);
            """)
    @staticmethod
    def _mandate_payload(row, positions):
        items=[{"code":p["code"],"quantity":int(p["quantity"]),"avgCost":float(p["avg_cost"]),"costBasis":int(p["quantity"])*float(p["avg_cost"]),"realizedPnL":float(p["realized_pnl"]),"updatedAt":p["updated_at"]} for p in positions if int(p["quantity"])>0 or abs(float(p["realized_pnl"]))>1e-9]
        invested=sum(x["costBasis"] for x in items if x["quantity"]>0); realized=sum(x["realizedPnL"] for x in items); cash=float(row["mandate_cash"])
        return {"mandateId":row["mandate_id"],"userId":row["user_id"],"accountType":"PAPER","allocatedCash":float(row["allocated_cash"]),"mandateCash":cash,"investedCost":invested,"accountingEquityAtCost":cash+invested,"realizedPnL":realized,"horizon":row["horizon"],"status":row["status"],"startsAt":row["starts_at"],"endsAt":row["ends_at"],"stopRequestedAt":row["stop_requested_at"],"completedAt":row["completed_at"],"createdAt":row["created_at"],"updatedAt":row["updated_at"],"positions":items}
    def _load_payload(self,conn,mid):
        row=conn.execute("SELECT * FROM kiasha_capital_mandates WHERE mandate_id=?",(mid,)).fetchone()
        if row is None: raise ValueError("Kiasha capital mandate not found")
        ps=conn.execute("SELECT * FROM kiasha_mandate_positions WHERE mandate_id=? ORDER BY code",(mid,)).fetchall(); return self._mandate_payload(row,ps)
    def active_mandate(self,*,user_id):
        with self._connect() as conn:
            row=conn.execute("SELECT mandate_id FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            return self._load_payload(conn,str(row["mandate_id"])) if row else None
    def create_mandate(self,*,user_id,allocated_cash,horizon,paper_cash_balance,now=None):
        amount=float(allocated_cash); paper=float(paper_cash_balance)
        if amount<=0: raise ValueError("allocated Kiasha capital must be positive")
        if amount>paper+1e-9: raise ValueError("allocated Kiasha capital exceeds available Paper cash")
        current=now or _now(); start=_iso(current); end=_iso(current+timedelta(days=_duration_days(horizon))); mid=f"kcm_{uuid4().hex}"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING')",(user_id,)).fetchone(): raise ValueError("user already has an active Kiasha capital mandate")
            conn.execute("INSERT INTO kiasha_capital_mandates(mandate_id,user_id,allocated_cash,mandate_cash,horizon,status,starts_at,ends_at,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?,?,?)",(mid,user_id,amount,amount,horizon,start,end,start,start)); payload=self._load_payload(conn,mid); conn.commit(); return payload
    def request_stop(self,*,user_id):
        current=_iso(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE"); row=conn.execute("SELECT mandate_id,status FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not row: raise ValueError("no active Kiasha capital mandate")
            mid=str(row["mandate_id"])
            if row["status"]=="ACTIVE": conn.execute("UPDATE kiasha_capital_mandates SET status='STOPPING',stop_requested_at=?,updated_at=? WHERE mandate_id=?",(current,current,mid))
            payload=self._load_payload(conn,mid); conn.commit(); return payload
    def manual_available_cash(self,*,user_id,paper_cash_balance):
        m=self.active_mandate(user_id=user_id); return max(0.0,float(paper_cash_balance)-(float(m["mandateCash"]) if m else 0.0))
    def assert_manual_buy_allowed(self,*,user_id,paper_cash_balance,cost):
        available=self.manual_available_cash(user_id=user_id,paper_cash_balance=paper_cash_balance)
        if float(cost)>available+1e-9: raise ValueError(f"manual Paper BUY would use Kiasha-reserved cash; manually available cash is {available:.0f}")
    def record_fill(self,*,user_id,intent_id,side,code,quantity,price,now=None):
        qty=int(quantity); px=float(price); symbol=str(code).strip().upper()
        if qty<=0 or px<=0: raise ValueError("mandate fill quantity and price must be positive")
        if not symbol: raise ValueError("mandate fill symbol is required")
        current=_iso(now or _now()); notional=qty*px
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE"); dup=conn.execute("SELECT mandate_id FROM kiasha_mandate_fills WHERE user_id=? AND intent_id=?",(user_id,intent_id)).fetchone()
            if dup: payload=self._load_payload(conn,str(dup["mandate_id"])); conn.rollback(); return payload
            m=conn.execute("SELECT * FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not m: raise ValueError("Kiasha Auto Invest requires an active capital mandate")
            mid=str(m["mandate_id"]); status=str(m["status"]); cash=float(m["mandate_cash"]); p=conn.execute("SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",(mid,symbol)).fetchone(); pq=int(p["quantity"]) if p else 0; pa=float(p["avg_cost"]) if p else 0.; rt=float(p["realized_pnl"]) if p else 0.; rf=0.
            if side=="BUY":
                if status!="ACTIVE": raise ValueError("Kiasha mandate is stopping; new BUYs are blocked")
                if notional>cash+1e-9: raise ValueError("Kiasha BUY exceeds remaining mandate cash")
                nq=pq+qty; na=((pq*pa)+notional)/nq; nc=cash-notional
            elif side=="SELL":
                if qty>pq: raise ValueError("Kiasha SELL exceeds mandate-owned position")
                rf=(px-pa)*qty; rt+=rf; nq=pq-qty; na=pa if nq>0 else 0.; nc=cash+notional
            else: raise ValueError("mandate fill side must be BUY or SELL")
            conn.execute("INSERT INTO kiasha_mandate_positions(mandate_id,code,quantity,avg_cost,realized_pnl,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(mandate_id,code) DO UPDATE SET quantity=excluded.quantity,avg_cost=excluded.avg_cost,realized_pnl=excluded.realized_pnl,updated_at=excluded.updated_at",(mid,symbol,nq,na,rt,current)); conn.execute("UPDATE kiasha_capital_mandates SET mandate_cash=?,updated_at=? WHERE mandate_id=?",(nc,current,mid)); conn.execute("INSERT INTO kiasha_mandate_fills(fill_id,mandate_id,user_id,intent_id,side,code,quantity,price,notional,realized_pnl,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(f"kcf_{uuid4().hex}",mid,user_id,intent_id,side,symbol,qty,px,notional,rf,current)); payload=self._load_payload(conn,mid); conn.commit(); return payload
    def complete_if_flat(self,*,user_id):
        current=_iso(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE"); row=conn.execute("SELECT mandate_id FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not row: conn.rollback(); return None
            mid=str(row["mandate_id"]); q=int(conn.execute("SELECT COALESCE(SUM(quantity),0) q FROM kiasha_mandate_positions WHERE mandate_id=?",(mid,)).fetchone()["q"])
            if q>0: payload=self._load_payload(conn,mid); conn.rollback(); return payload
            conn.execute("UPDATE kiasha_capital_mandates SET status='COMPLETED',completed_at=?,updated_at=? WHERE mandate_id=?",(current,current,mid)); payload=self._load_payload(conn,mid); conn.commit(); return payload
    def aggregate_profile(self) -> dict[str,Any]:
        """Aggregate Kiasha delegated capital without mixing Paper and real money."""
        with self._connect() as conn:
            active=conn.execute("SELECT mandate_id,user_id,allocated_cash,mandate_cash FROM kiasha_capital_mandates WHERE status IN('ACTIVE','STOPPING')").fetchall()
            mids=[str(r["mandate_id"]) for r in active]
            invested=0.0
            if mids:
                marks=','.join('?' for _ in mids)
                rows=conn.execute(f"SELECT quantity,avg_cost FROM kiasha_mandate_positions WHERE mandate_id IN ({marks}) AND quantity>0",mids).fetchall(); invested=sum(int(r["quantity"])*float(r["avg_cost"]) for r in rows)
            allocated=sum(float(r["allocated_cash"]) for r in active); cash=sum(float(r["mandate_cash"]) for r in active); users=len({str(r["user_id"]) for r in active})
        paper={"users":users,"allocatedCapital":allocated,"uninvestedCash":cash,"investedCost":invested,"accountingEquityAtCost":cash+invested,"currency":"IRR","valuation":"cost"}
        real={"users":0,"allocatedCapital":0.0,"investedValue":0.0,"cash":0.0,"currency":"IRR","available":False,"reason":"No authorized live broker/custody integration is connected; real client assets must not be fabricated."}
        return {"paper":paper,"real":real,"combinedNominal":None,"combinedDisplayAllowed":False,"note":"Paper and real assets are intentionally not summed into one money figure. Show both buckets and user counts separately."}

STORE=KiashaCapitalMandateStore()
