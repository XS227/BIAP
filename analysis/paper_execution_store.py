"""Atomic persistence for Kiasha Paper-only BUY fills.

The shared Paper cash/position ledger and Kiasha mandate sub-ledger are mutated
inside the same SQLite transaction. ``horizon == 'manual'`` identifies a
user-initiated Paper trade; every other horizon is Kiasha-owned execution.
"""
from __future__ import annotations
from datetime import datetime, time, timedelta, timezone
import json, sqlite3
from typing import Any, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo
from audit_store import DEFAULT_DB_PATH
from risk import load_policy

_TSE_TZ=ZoneInfo("Asia/Tehran")
def _tehran_day_bounds_utc(now_utc:datetime):
    local_day=now_utc.astimezone(_TSE_TZ).date(); start_local=datetime.combine(local_day,time.min,tzinfo=_TSE_TZ); end_local=start_local+timedelta(days=1)
    return start_local.astimezone(timezone.utc).isoformat(),end_local.astimezone(timezone.utc).isoformat()

class PaperExecutionStore:
    def __init__(self,db_path:str=DEFAULT_DB_PATH): self.db_path=db_path
    def _connect(self):
        c=sqlite3.connect(self.db_path,timeout=30); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); return c
    @staticmethod
    def _user_daily_paper_notional(conn,*,user_id,now_utc):
        start,end=_tehran_day_bounds_utc(now_utc); rows=conn.execute("SELECT payload_json FROM audit_events WHERE user_id=? AND event_type='KIASHA_AI_PAPER_FILLED' AND created_at>=? AND created_at<?",(user_id,start,end)).fetchall(); total=0.0
        for r in rows:
            try: total+=max(0.0,float(json.loads(r["payload_json"]).get("fillCost") or 0.0))
            except (TypeError,ValueError,json.JSONDecodeError): return float("inf")
        return total
    @staticmethod
    def _user_daily_realized_loss(conn,*,user_id,now_utc):
        start,end=_tehran_day_bounds_utc(now_utc); rows=conn.execute("SELECT payload_json FROM audit_events WHERE user_id=? AND event_type='KIASHA_AI_PAPER_SOLD' AND created_at>=? AND created_at<?",(user_id,start,end)).fetchall(); total=0.0
        for r in rows:
            try: total+=max(0.0,-float(json.loads(r["payload_json"]).get("realizedPnL") or 0.0))
            except (TypeError,ValueError,json.JSONDecodeError): return float("inf")
        return total
    def daily_realized_loss_used(self,*,user_id,now_utc:Optional[datetime]=None):
        c=self._connect()
        try:return self._user_daily_realized_loss(c,user_id=user_id,now_utc=now_utc or datetime.now(timezone.utc))
        finally:c.close()
    @staticmethod
    def _active_mandate(conn,user_id):
        try:return conn.execute("SELECT * FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
        except sqlite3.OperationalError:return None
    def commit_buy_fill(self,*,user_id:str,code:str,horizon:str,proposal:dict[str,Any],risk:dict[str,Any],intent:dict[str,Any],receipt:dict[str,Any],reference_price:float,reference_source:str,idempotency_key:str)->dict[str,Any]:
        if receipt.get("broker")!="paper" or receipt.get("status")!="PAPER_FILLED": raise ValueError("only PAPER_FILLED receipts from PaperBroker are accepted")
        if intent.get("mode")!="paper" or intent.get("side")!="BUY": raise ValueError("only paper BUY intents are accepted")
        quantity=int(intent.get("quantity") or 0); price=float(reference_price)
        if quantity<=0: raise ValueError("paper quantity must be positive")
        if price<=0: raise ValueError("verified reference price must be positive")
        cost=quantity*price; now_utc=datetime.now(timezone.utc); now=now_utc.isoformat(); symbol=code.upper(); manual=horizon=="manual"
        conn=self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing=conn.execute("SELECT response_json FROM idempotency_keys WHERE user_id=? AND idempotency_key=?",(user_id,idempotency_key)).fetchone()
            if existing is not None: conn.rollback(); return json.loads(existing["response_json"])
            account=conn.execute("SELECT initial_cash,cash_balance,created_at FROM paper_accounts WHERE user_id=?",(user_id,)).fetchone()
            if account is None: raise ValueError("server-owned Paper account does not exist")
            cash_before=float(account["cash_balance"])
            if cost>cash_before+1e-9: raise ValueError("insufficient Paper cash balance")
            mandate=self._active_mandate(conn,user_id)
            mandate_id=None
            if manual:
                reserved=float(mandate["mandate_cash"]) if mandate is not None else 0.0
                available=max(0.0,cash_before-reserved)
                if cost>available+1e-9: raise ValueError(f"manual Paper BUY would use Kiasha-reserved cash; manually available cash is {available:.0f}")
            else:
                if mandate is None: raise ValueError("Kiasha Paper BUY requires an active capital mandate")
                if str(mandate["status"])!="ACTIVE": raise ValueError("Kiasha capital mandate is stopping; new BUYs are blocked")
                if cost>float(mandate["mandate_cash"])+1e-9: raise ValueError("Kiasha BUY exceeds remaining mandate cash")
                mandate_id=str(mandate["mandate_id"])
            policy=load_policy(); daily_before=self._user_daily_paper_notional(conn,user_id=user_id,now_utc=now_utc)
            if daily_before+cost>policy.max_daily_notional+1e-9: raise ValueError(f"projected user Paper daily notional exceeds max {policy.max_daily_notional:.0f}")
            loss_before=self._user_daily_realized_loss(conn,user_id=user_id,now_utc=now_utc)
            if loss_before>=policy.max_daily_realized_loss: raise ValueError(f"today's realized Paper losses of {loss_before:.0f} have reached the max daily realized loss {policy.max_daily_realized_loss:.0f} -- new Paper BUYs are paused until the next session")
            prior=conn.execute("SELECT quantity,avg_cost FROM paper_positions WHERE user_id=? AND code=?",(user_id,symbol)).fetchone(); prior_qty=int(prior["quantity"]) if prior else 0; prior_avg=float(prior["avg_cost"]) if prior else 0.0; new_qty=prior_qty+quantity; new_avg=((prior_qty*prior_avg)+cost)/new_qty; cash_after=cash_before-cost
            conn.execute("UPDATE paper_accounts SET cash_balance=?,updated_at=? WHERE user_id=?",(cash_after,now,user_id)); conn.execute("INSERT INTO paper_positions(user_id,code,quantity,avg_cost,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,code) DO UPDATE SET quantity=excluded.quantity,avg_cost=excluded.avg_cost,updated_at=excluded.updated_at",(user_id,symbol,new_qty,new_avg,now))
            if mandate_id is not None:
                mp=conn.execute("SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",(mandate_id,symbol)).fetchone(); mq=int(mp["quantity"]) if mp else 0; ma=float(mp["avg_cost"]) if mp else 0.0; mr=float(mp["realized_pnl"]) if mp else 0.0; mnq=mq+quantity; mna=((mq*ma)+cost)/mnq; mcash=float(mandate["mandate_cash"])-cost
                conn.execute("INSERT INTO kiasha_mandate_positions(mandate_id,code,quantity,avg_cost,realized_pnl,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(mandate_id,code) DO UPDATE SET quantity=excluded.quantity,avg_cost=excluded.avg_cost,realized_pnl=excluded.realized_pnl,updated_at=excluded.updated_at",(mandate_id,symbol,mnq,mna,mr,now)); conn.execute("UPDATE kiasha_capital_mandates SET mandate_cash=?,updated_at=? WHERE mandate_id=?",(mcash,now,mandate_id)); conn.execute("INSERT INTO kiasha_mandate_fills(fill_id,mandate_id,user_id,intent_id,side,code,quantity,price,notional,realized_pnl,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(f"kcf_{uuid4().hex}",mandate_id,user_id,intent["id"],"BUY",symbol,quantity,price,cost,0.0,now))
            persisted={**receipt,"status":"PAPER_FILLED"}; conn.execute("INSERT INTO order_intents(id,user_id,code,side,quantity,limit_price,mode,status,recommendation_call,recommendation_score,created_at,updated_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(intent["id"],user_id,intent["code"],intent["side"],quantity,intent.get("limit_price"),intent["mode"],persisted["status"],intent["recommendation_call"],intent["recommendation_score"],intent["created_at"],now,json.dumps(persisted,ensure_ascii=False,sort_keys=True)))
            decision_id=f"kai_{uuid4().hex}"; result={"allowed":True,"reasons":[],"proposal":proposal,"risk":risk,"intent":intent,"receipt":persisted,"paperExecution":True,"liveExecution":False,"dryRun":False,"decisionId":decision_id,"referencePrice":price,"referencePriceSource":reference_source,"fillCost":cost,"executionOwner":"manual" if manual else "kiasha","kiashaMandateId":mandate_id,"dailyNotionalBefore":daily_before,"dailyNotionalAfter":daily_before+cost,"dailyNotionalLimit":policy.max_daily_notional,"dailyRealizedLoss":loss_before,"dailyRealizedLossLimit":policy.max_daily_realized_loss,"accountAfter":{"userId":user_id,"initialCash":float(account["initial_cash"]),"cashBalance":cash_after,"positions":[{"code":symbol,"quantity":new_qty,"avgCost":new_avg,"updatedAt":now}]}}
            conn.execute("INSERT INTO kiasha_ai_decisions(decision_id,user_id,code,horizon,allowed,dry_run,reference_price,reference_source,created_at,proposal_json,risk_json,result_json) VALUES(?,?,?,?,1,0,?,?,?,?,?,?)",(decision_id,user_id,symbol,horizon,price,reference_source,now,json.dumps(proposal,ensure_ascii=False,sort_keys=True),json.dumps(risk,ensure_ascii=False,sort_keys=True),json.dumps(result,ensure_ascii=False,sort_keys=True)))
            event_type="MANUAL_PAPER_FILLED" if manual else "KIASHA_AI_PAPER_FILLED"; payload={"decisionId":decision_id,"code":symbol,"horizon":horizon,"quantity":quantity,"price":price,"fillCost":cost,"executionOwner":result["executionOwner"],"kiashaMandateId":mandate_id,"dailyNotionalBefore":daily_before,"dailyNotionalAfter":daily_before+cost,"dailyNotionalLimit":policy.max_daily_notional,"cashBefore":cash_before,"cashAfter":cash_after,"broker":"paper"}
            conn.execute("INSERT INTO audit_events(event_id,user_id,intent_id,event_type,created_at,payload_json) VALUES(?,?,?,?,?,?)",(f"evt_{uuid4().hex}",user_id,intent["id"],event_type,now,json.dumps(payload,ensure_ascii=False,sort_keys=True))); conn.execute("INSERT INTO idempotency_keys(user_id,idempotency_key,intent_id,response_json,created_at) VALUES(?,?,?,?,?)",(user_id,idempotency_key,intent["id"],json.dumps(result,ensure_ascii=False,sort_keys=True),now)); conn.commit(); return result
        except Exception:
            conn.rollback(); raise
        finally: conn.close()
