"""Kiasha capital mandates and isolated accounting.

Paper mandates are implemented today. Paper and real client assets remain
separate. Kiasha performance snapshots require verified marks for every open
mandate position; incomplete valuations are never guessed.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Literal
from uuid import uuid4
from audit_store import DEFAULT_DB_PATH

Horizon = Literal["week", "month"]
def _now(): return datetime.now(timezone.utc)
def _iso(v): return v.astimezone(timezone.utc).isoformat()
def _duration_days(h):
    if h=="week": return 7
    if h=="month": return 30
    raise ValueError("horizon must be week or month")

class KiashaCapitalMandateStore:
    def __init__(self,db_path: str=DEFAULT_DB_PATH): self.db_path=db_path; self._init_db()
    def _connect(self):
        c=sqlite3.connect(self.db_path,timeout=30);c.row_factory=sqlite3.Row;c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA foreign_keys=ON");return c
    def _init_db(self):
        with self._connect() as c:c.executescript("""
        CREATE TABLE IF NOT EXISTS kiasha_capital_mandates(mandate_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,allocated_cash REAL NOT NULL CHECK(allocated_cash>0),mandate_cash REAL NOT NULL CHECK(mandate_cash>=0),horizon TEXT NOT NULL CHECK(horizon IN('week','month')),status TEXT NOT NULL CHECK(status IN('ACTIVE','STOPPING','COMPLETED')),starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,stop_requested_at TEXT,completed_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_user_status ON kiasha_capital_mandates(user_id,status,created_at);
        CREATE TABLE IF NOT EXISTS kiasha_mandate_positions(mandate_id TEXT NOT NULL,code TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>=0),avg_cost REAL NOT NULL CHECK(avg_cost>=0),realized_pnl REAL NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(mandate_id,code),FOREIGN KEY(mandate_id) REFERENCES kiasha_capital_mandates(mandate_id));
        CREATE TABLE IF NOT EXISTS kiasha_mandate_fills(fill_id TEXT PRIMARY KEY,mandate_id TEXT NOT NULL,user_id TEXT NOT NULL,intent_id TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN('BUY','SELL')),code TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),price REAL NOT NULL CHECK(price>0),notional REAL NOT NULL CHECK(notional>0),realized_pnl REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(user_id,intent_id),FOREIGN KEY(mandate_id) REFERENCES kiasha_capital_mandates(mandate_id));
        CREATE INDEX IF NOT EXISTS idx_kiasha_mandate_fills_mandate ON kiasha_mandate_fills(mandate_id,created_at);
        CREATE TABLE IF NOT EXISTS kiasha_mandate_equity_snapshots(snapshot_id TEXT PRIMARY KEY,mandate_id TEXT NOT NULL,user_id TEXT NOT NULL,snapshot_date TEXT NOT NULL,mandate_cash REAL NOT NULL,positions_value REAL NOT NULL,total_equity REAL NOT NULL,allocated_cash REAL NOT NULL,realized_pnl REAL NOT NULL,created_at TEXT NOT NULL,UNIQUE(mandate_id,snapshot_date),FOREIGN KEY(mandate_id) REFERENCES kiasha_capital_mandates(mandate_id));
        CREATE INDEX IF NOT EXISTS idx_kiasha_equity_user_date ON kiasha_mandate_equity_snapshots(user_id,snapshot_date,created_at);
        """)
    @staticmethod
    def _mandate_payload(r,ps):
        items=[{"code":p["code"],"quantity":int(p["quantity"]),"avgCost":float(p["avg_cost"]),"costBasis":int(p["quantity"])*float(p["avg_cost"]),"realizedPnL":float(p["realized_pnl"]),"updatedAt":p["updated_at"]} for p in ps if int(p["quantity"])>0 or abs(float(p["realized_pnl"]))>1e-9];invested=sum(x["costBasis"] for x in items if x["quantity"]>0);realized=sum(x["realizedPnL"] for x in items);cash=float(r["mandate_cash"])
        return {"mandateId":r["mandate_id"],"userId":r["user_id"],"accountType":"PAPER","allocatedCash":float(r["allocated_cash"]),"mandateCash":cash,"investedCost":invested,"accountingEquityAtCost":cash+invested,"realizedPnL":realized,"horizon":r["horizon"],"status":r["status"],"startsAt":r["starts_at"],"endsAt":r["ends_at"],"stopRequestedAt":r["stop_requested_at"],"completedAt":r["completed_at"],"createdAt":r["created_at"],"updatedAt":r["updated_at"],"positions":items}
    def _load_payload(self,c,mid):
        r=c.execute("SELECT * FROM kiasha_capital_mandates WHERE mandate_id=?",(mid,)).fetchone()
        if r is None: raise ValueError("Kiasha capital mandate not found")
        return self._mandate_payload(r,c.execute("SELECT * FROM kiasha_mandate_positions WHERE mandate_id=? ORDER BY code",(mid,)).fetchall())
    def active_mandate(self,*,user_id):
        with self._connect() as c:
            r=c.execute("SELECT mandate_id FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone();return self._load_payload(c,str(r["mandate_id"])) if r else None
    def create_mandate(self,*,user_id,allocated_cash,horizon,paper_cash_balance,now=None):
        a=float(allocated_cash);paper=float(paper_cash_balance)
        if a<=0:raise ValueError("allocated Kiasha capital must be positive")
        if a>paper+1e-9:raise ValueError("allocated Kiasha capital exceeds available Paper cash")
        cur=now or _now();start=_iso(cur);end=_iso(cur+timedelta(days=_duration_days(horizon)));mid=f"kcm_{uuid4().hex}"
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING')",(user_id,)).fetchone():raise ValueError("user already has an active Kiasha capital mandate")
            c.execute("INSERT INTO kiasha_capital_mandates(mandate_id,user_id,allocated_cash,mandate_cash,horizon,status,starts_at,ends_at,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?,?,?)",(mid,user_id,a,a,horizon,start,end,start,start));p=self._load_payload(c,mid);c.commit();return p
    def request_stop(self,*,user_id):
        cur=_iso(_now())
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE");r=c.execute("SELECT mandate_id,status FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not r:raise ValueError("no active Kiasha capital mandate")
            mid=str(r["mandate_id"])
            if r["status"]=="ACTIVE":c.execute("UPDATE kiasha_capital_mandates SET status='STOPPING',stop_requested_at=?,updated_at=? WHERE mandate_id=?",(cur,cur,mid))
            p=self._load_payload(c,mid);c.commit();return p
    def manual_available_cash(self,*,user_id,paper_cash_balance):
        m=self.active_mandate(user_id=user_id);return max(0.0,float(paper_cash_balance)-(float(m["mandateCash"]) if m else 0.0))
    def assert_manual_buy_allowed(self,*,user_id,paper_cash_balance,cost):
        a=self.manual_available_cash(user_id=user_id,paper_cash_balance=paper_cash_balance)
        if float(cost)>a+1e-9:raise ValueError(f"manual Paper BUY would use Kiasha-reserved cash; manually available cash is {a:.0f}")
    def record_fill(self,*,user_id,intent_id,side,code,quantity,price,now=None):
        q=int(quantity);px=float(price);sym=str(code).strip().upper()
        if q<=0 or px<=0:raise ValueError("mandate fill quantity and price must be positive")
        if not sym:raise ValueError("mandate fill symbol is required")
        cur=_iso(now or _now());notional=q*px
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE");dup=c.execute("SELECT mandate_id FROM kiasha_mandate_fills WHERE user_id=? AND intent_id=?",(user_id,intent_id)).fetchone()
            if dup:p=self._load_payload(c,str(dup["mandate_id"]));c.rollback();return p
            m=c.execute("SELECT * FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not m:raise ValueError("Kiasha Auto Invest requires an active capital mandate")
            mid=str(m["mandate_id"]);status=str(m["status"]);cash=float(m["mandate_cash"]);p=c.execute("SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",(mid,sym)).fetchone();pq=int(p["quantity"]) if p else 0;pa=float(p["avg_cost"]) if p else 0.;rt=float(p["realized_pnl"]) if p else 0.;rf=0.
            if side=="BUY":
                if status!="ACTIVE":raise ValueError("Kiasha mandate is stopping; new BUYs are blocked")
                if notional>cash+1e-9:raise ValueError("Kiasha BUY exceeds remaining mandate cash")
                nq=pq+q;na=((pq*pa)+notional)/nq;nc=cash-notional
            elif side=="SELL":
                if q>pq:raise ValueError("Kiasha SELL exceeds mandate-owned position")
                rf=(px-pa)*q;rt+=rf;nq=pq-q;na=pa if nq>0 else 0.;nc=cash+notional
            else:raise ValueError("mandate fill side must be BUY or SELL")
            c.execute("INSERT INTO kiasha_mandate_positions(mandate_id,code,quantity,avg_cost,realized_pnl,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(mandate_id,code) DO UPDATE SET quantity=excluded.quantity,avg_cost=excluded.avg_cost,realized_pnl=excluded.realized_pnl,updated_at=excluded.updated_at",(mid,sym,nq,na,rt,cur));c.execute("UPDATE kiasha_capital_mandates SET mandate_cash=?,updated_at=? WHERE mandate_id=?",(nc,cur,mid));c.execute("INSERT INTO kiasha_mandate_fills(fill_id,mandate_id,user_id,intent_id,side,code,quantity,price,notional,realized_pnl,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(f"kcf_{uuid4().hex}",mid,user_id,intent_id,side,sym,q,px,notional,rf,cur));out=self._load_payload(c,mid);c.commit();return out
    def record_verified_equity_snapshot(self,*,user_id,prices,snapshot_date=None,now=None):
        """Persist one daily Kiasha mark only when every open position has a verified positive price."""
        cur=now or _now();day=snapshot_date or cur.date().isoformat();m=self.active_mandate(user_id=user_id)
        if not m:return None
        value=0.0
        for p in m["positions"]:
            q=int(p["quantity"])
            if q<=0:continue
            px=prices.get(str(p["code"]).upper())
            if px is None or not isinstance(px,(int,float)) or float(px)<=0:return None
            value+=q*float(px)
        total=float(m["mandateCash"])+value;created=_iso(cur)
        with self._connect() as c:
            c.execute("INSERT INTO kiasha_mandate_equity_snapshots(snapshot_id,mandate_id,user_id,snapshot_date,mandate_cash,positions_value,total_equity,allocated_cash,realized_pnl,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mandate_id,snapshot_date) DO UPDATE SET mandate_cash=excluded.mandate_cash,positions_value=excluded.positions_value,total_equity=excluded.total_equity,allocated_cash=excluded.allocated_cash,realized_pnl=excluded.realized_pnl,created_at=excluded.created_at",(f"kes_{uuid4().hex}",m["mandateId"],user_id,day,float(m["mandateCash"]),value,total,float(m["allocatedCash"]),float(m["realizedPnL"]),created))
        return {"mandateId":m["mandateId"],"userId":user_id,"snapshotDate":day,"mandateCash":float(m["mandateCash"]),"positionsValue":value,"totalEquity":total,"allocatedCash":float(m["allocatedCash"]),"realizedPnL":float(m["realizedPnL"]),"createdAt":created}
    def list_equity_snapshots(self,*,user_id,limit=400):
        with self._connect() as c:rows=c.execute("SELECT * FROM kiasha_mandate_equity_snapshots WHERE user_id=? ORDER BY snapshot_date DESC,created_at DESC LIMIT ?",(user_id,int(limit))).fetchall()
        return [{"mandateId":r["mandate_id"],"userId":r["user_id"],"snapshotDate":r["snapshot_date"],"mandateCash":float(r["mandate_cash"]),"positionsValue":float(r["positions_value"]),"totalEquity":float(r["total_equity"]),"allocatedCash":float(r["allocated_cash"]),"realizedPnL":float(r["realized_pnl"]),"createdAt":r["created_at"]} for r in rows]
    def complete_if_flat(self,*,user_id):
        cur=_iso(_now())
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE");r=c.execute("SELECT mandate_id FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if not r:c.rollback();return None
            mid=str(r["mandate_id"]);q=int(c.execute("SELECT COALESCE(SUM(quantity),0) q FROM kiasha_mandate_positions WHERE mandate_id=?",(mid,)).fetchone()["q"])
            if q>0:p=self._load_payload(c,mid);c.rollback();return p
            c.execute("UPDATE kiasha_capital_mandates SET status='COMPLETED',completed_at=?,updated_at=? WHERE mandate_id=?",(cur,cur,mid));p=self._load_payload(c,mid);c.commit();return p
    def aggregate_profile(self)->dict[str,Any]:
        with self._connect() as c:
            active=c.execute("SELECT mandate_id,user_id,allocated_cash,mandate_cash FROM kiasha_capital_mandates WHERE status IN('ACTIVE','STOPPING')").fetchall();mids=[str(r["mandate_id"]) for r in active];invested=0.
            if mids:
                marks=','.join('?' for _ in mids);rows=c.execute(f"SELECT quantity,avg_cost FROM kiasha_mandate_positions WHERE mandate_id IN ({marks}) AND quantity>0",mids).fetchall();invested=sum(int(r["quantity"])*float(r["avg_cost"]) for r in rows)
            allocated=sum(float(r["allocated_cash"]) for r in active);cash=sum(float(r["mandate_cash"]) for r in active);users=len({str(r["user_id"]) for r in active})
        return {"paper":{"users":users,"allocatedCapital":allocated,"uninvestedCash":cash,"investedCost":invested,"accountingEquityAtCost":cash+invested,"currency":"IRR","valuation":"cost"},"real":{"users":0,"allocatedCapital":0.,"investedValue":0.,"cash":0.,"currency":"IRR","available":False,"reason":"No authorized live broker/custody integration is connected; real client assets must not be fabricated."},"combinedNominal":None,"combinedDisplayAllowed":False,"note":"Paper and real assets are intentionally not summed into one money figure."}
STORE=KiashaCapitalMandateStore()
