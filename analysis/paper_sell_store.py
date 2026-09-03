"""Atomic server-owned Paper SELL persistence with Kiasha sub-ledger ownership."""
from __future__ import annotations
from datetime import datetime, timezone
import json, sqlite3
from typing import Any
from uuid import uuid4
from audit_store import DEFAULT_DB_PATH

class PaperSellStore:
    def __init__(self,db_path:str=DEFAULT_DB_PATH): self.db_path=db_path
    def _connect(self):
        c=sqlite3.connect(self.db_path,timeout=30); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); return c
    @staticmethod
    def _active_mandate(conn,user_id):
        try:return conn.execute("SELECT * FROM kiasha_capital_mandates WHERE user_id=? AND status IN('ACTIVE','STOPPING') ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
        except sqlite3.OperationalError:return None
    def commit_sell_fill(self,*,user_id:str,code:str,horizon:str,proposal:dict[str,Any],risk:dict[str,Any],intent:dict[str,Any],receipt:dict[str,Any],reference_price:float,reference_source:str,idempotency_key:str)->dict[str,Any]:
        if receipt.get("broker")!="paper" or receipt.get("status")!="PAPER_FILLED": raise ValueError("only PAPER_FILLED receipts from PaperBroker are accepted")
        if intent.get("mode")!="paper" or intent.get("side")!="SELL": raise ValueError("only paper SELL intents are accepted")
        quantity=int(intent.get("quantity") or 0); price=float(reference_price)
        if quantity<=0 or price<=0: raise ValueError("positive quantity and verified price are required")
        now=datetime.now(timezone.utc).isoformat(); symbol=code.upper(); manual=horizon=="manual"
        conn=self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing=conn.execute("SELECT response_json FROM idempotency_keys WHERE user_id=? AND idempotency_key=?",(user_id,idempotency_key)).fetchone()
            if existing is not None: conn.rollback(); return json.loads(existing["response_json"])
            account=conn.execute("SELECT initial_cash,cash_balance FROM paper_accounts WHERE user_id=?",(user_id,)).fetchone(); position=conn.execute("SELECT quantity,avg_cost FROM paper_positions WHERE user_id=? AND code=?",(user_id,symbol)).fetchone()
            if account is None: raise ValueError("server-owned Paper account does not exist")
            if position is None or int(position["quantity"])<=0: raise ValueError("Paper position is not owned by this account")
            owned=int(position["quantity"]); mandate=self._active_mandate(conn,user_id); mandate_id=None; mandate_realized=None
            mandate_qty=0
            if mandate is not None:
                mp=conn.execute("SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",(str(mandate["mandate_id"]),symbol)).fetchone(); mandate_qty=int(mp["quantity"]) if mp else 0
            if manual:
                manual_owned=max(0,owned-mandate_qty)
                if quantity>manual_owned: raise ValueError(f"manual Paper SELL would use Kiasha-owned shares; manually sellable quantity is {manual_owned}")
            else:
                if mandate is None: raise ValueError("Kiasha Paper SELL requires an active capital mandate")
                mandate_id=str(mandate["mandate_id"])
                if quantity>mandate_qty: raise ValueError("Kiasha SELL exceeds mandate-owned position")
            if quantity>owned: raise ValueError("SELL quantity exceeds owned Paper position")
            proceeds=quantity*price; shared_avg=float(position["avg_cost"]); shared_realized=quantity*(price-shared_avg); remaining=owned-quantity; cash_before=float(account["cash_balance"]); cash_after=cash_before+proceeds
            conn.execute("UPDATE paper_accounts SET cash_balance=?,updated_at=? WHERE user_id=?",(cash_after,now,user_id))
            if remaining==0: conn.execute("DELETE FROM paper_positions WHERE user_id=? AND code=?",(user_id,symbol))
            else: conn.execute("UPDATE paper_positions SET quantity=?,updated_at=? WHERE user_id=? AND code=?",(remaining,now,user_id,symbol))
            realized_pnl=shared_realized
            if mandate_id is not None:
                mp=conn.execute("SELECT quantity,avg_cost,realized_pnl FROM kiasha_mandate_positions WHERE mandate_id=? AND code=?",(mandate_id,symbol)).fetchone(); mqty=int(mp["quantity"]); mavg=float(mp["avg_cost"]); mreal=float(mp["realized_pnl"]); mandate_realized=quantity*(price-mavg); mremaining=mqty-quantity; mreal+=mandate_realized; mcash=float(mandate["mandate_cash"])+proceeds
                conn.execute("UPDATE kiasha_mandate_positions SET quantity=?,avg_cost=?,realized_pnl=?,updated_at=? WHERE mandate_id=? AND code=?",(mremaining,mavg if mremaining>0 else 0.0,mreal,now,mandate_id,symbol)); conn.execute("UPDATE kiasha_capital_mandates SET mandate_cash=?,updated_at=? WHERE mandate_id=?",(mcash,now,mandate_id)); conn.execute("INSERT INTO kiasha_mandate_fills(fill_id,mandate_id,user_id,intent_id,side,code,quantity,price,notional,realized_pnl,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(f"kcf_{uuid4().hex}",mandate_id,user_id,intent["id"],"SELL",symbol,quantity,price,proceeds,mandate_realized,now)); realized_pnl=mandate_realized
            persisted={**receipt,"status":"PAPER_FILLED"}; conn.execute("INSERT INTO order_intents(id,user_id,code,side,quantity,limit_price,mode,status,recommendation_call,recommendation_score,created_at,updated_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(intent["id"],user_id,intent["code"],"SELL",quantity,intent.get("limit_price"),"paper","PAPER_FILLED",intent["recommendation_call"],intent["recommendation_score"],intent["created_at"],now,json.dumps(persisted,ensure_ascii=False,sort_keys=True)))
            decision_id=f"kai_{uuid4().hex}"; result={"allowed":True,"reasons":[],"proposal":proposal,"risk":risk,"intent":intent,"receipt":persisted,"paperExecution":True,"liveExecution":False,"dryRun":False,"decisionId":decision_id,"referencePrice":price,"referencePriceSource":reference_source,"fillProceeds":proceeds,"realizedPnL":realized_pnl,"executionOwner":"manual" if manual else "kiasha","kiashaMandateId":mandate_id,"accountAfter":{"userId":user_id,"initialCash":float(account["initial_cash"]),"cashBalance":cash_after,"soldCode":symbol,"remainingQuantity":remaining}}
            conn.execute("INSERT INTO kiasha_ai_decisions(decision_id,user_id,code,horizon,allowed,dry_run,reference_price,reference_source,created_at,proposal_json,risk_json,result_json) VALUES(?,?,?,?,1,0,?,?,?,?,?,?)",(decision_id,user_id,symbol,horizon,price,reference_source,now,json.dumps(proposal,ensure_ascii=False,sort_keys=True),json.dumps(risk,ensure_ascii=False,sort_keys=True),json.dumps(result,ensure_ascii=False,sort_keys=True)))
            event_type="MANUAL_PAPER_SOLD" if manual else "KIASHA_AI_PAPER_SOLD"; payload={"decisionId":decision_id,"code":symbol,"horizon":horizon,"quantity":quantity,"price":price,"proceeds":proceeds,"realizedPnL":realized_pnl,"executionOwner":result["executionOwner"],"kiashaMandateId":mandate_id,"cashBefore":cash_before,"cashAfter":cash_after,"remainingQuantity":remaining,"broker":"paper"}
            conn.execute("INSERT INTO audit_events(event_id,user_id,intent_id,event_type,created_at,payload_json) VALUES(?,?,?,?,?,?)",(f"evt_{uuid4().hex}",user_id,intent["id"],event_type,now,json.dumps(payload,ensure_ascii=False,sort_keys=True))); conn.execute("INSERT INTO idempotency_keys(user_id,idempotency_key,intent_id,response_json,created_at) VALUES(?,?,?,?,?)",(user_id,idempotency_key,intent["id"],json.dumps(result,ensure_ascii=False,sort_keys=True),now)); conn.commit(); return result
        except Exception:
            conn.rollback(); raise
        finally: conn.close()
