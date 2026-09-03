"""Authenticated API for delegating Paper capital to Kiasha.

These routes create and stop Paper mandates only. They never accept live money.
"""
import os
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from audit_store import AuditStore
from auth import require_user_id
from kiasha_capital_mandate import STORE

router=APIRouter(prefix="/ai/capital-mandate",tags=["performance"])
AUDIT=AuditStore()
DEFAULT_PAPER_INITIAL_CASH=float(os.getenv("KIASHA_PAPER_INITIAL_CASH","100000000"))

class CreateMandateRequest(BaseModel):
    allocatedCash: float = Field(gt=0)
    horizon: Literal["week","month"]

@router.get("")
def capital_mandate_status(user_id:str=Depends(require_user_id)):
    account=AUDIT.ensure_paper_account(user_id=str(user_id),initial_cash=DEFAULT_PAPER_INITIAL_CASH)
    mandate=STORE.active_mandate(user_id=str(user_id))
    return {"mandate":mandate,"paperCashBalance":float(account["cashBalance"]),"manualAvailableCash":STORE.manual_available_cash(user_id=str(user_id),paper_cash_balance=float(account["cashBalance"])),"paperOnly":True,"liveExecution":False}

@router.post("")
def create_capital_mandate(req:CreateMandateRequest,user_id:str=Depends(require_user_id)):
    account=AUDIT.ensure_paper_account(user_id=str(user_id),initial_cash=DEFAULT_PAPER_INITIAL_CASH)
    try:
        mandate=STORE.create_mandate(user_id=str(user_id),allocated_cash=req.allocatedCash,horizon=req.horizon,paper_cash_balance=float(account["cashBalance"]))
    except ValueError as exc:
        raise HTTPException(status_code=409,detail=str(exc)) from exc
    return {"mandate":mandate,"paperCashBalance":float(account["cashBalance"]),"manualAvailableCash":STORE.manual_available_cash(user_id=str(user_id),paper_cash_balance=float(account["cashBalance"])),"paperOnly":True,"liveExecution":False}

@router.post("/stop")
def stop_capital_mandate(user_id:str=Depends(require_user_id)):
    try: mandate=STORE.request_stop(user_id=str(user_id))
    except ValueError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    account=AUDIT.ensure_paper_account(user_id=str(user_id),initial_cash=DEFAULT_PAPER_INITIAL_CASH)
    return {"mandate":mandate,"manualAvailableCash":STORE.manual_available_cash(user_id=str(user_id),paper_cash_balance=float(account["cashBalance"])),"note":"New Kiasha BUYs are blocked. Existing Kiasha positions remain Kiasha-owned until sold or otherwise safely unwound.","paperOnly":True,"liveExecution":False}
