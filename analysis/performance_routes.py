"""Read-only performance routes plus guarded Kiasha Paper simulation APIs."""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from audit_store import AuditStore
from auth import require_user_id
from execution import submit_order_intent
from kiasha_ai import analyze as analyze_with_ai, status as kiasha_ai_status
from kiasha_auto_invest import auto_status, run_user_auto_invest, update_auto_settings
from kiasha_paper import evaluate_ai_paper_proposal
from market_data import MarketDataUnavailable, find_quote
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from symbol_universe import SymbolUniverseUnavailable, query_symbols

router = APIRouter(prefix="/performance", tags=["performance"])
STORE = PerformanceStore()
AUDIT_STORE = AuditStore()
PAPER_EXECUTION_STORE = PaperExecutionStore()
PAPER_SELL_STORE = PaperSellStore()
AGENTS = ("fundamental", "risk", "forecast", "comparison")
DEFAULT_PAPER_INITIAL_CASH = float(os.getenv("KIASHA_PAPER_INITIAL_CASH", "100000000"))

class AutoInvestSettingsRequest(BaseModel):
    enabled: bool
    horizon: Literal["short", "long"] = "short"
    maxDailyTrades: int = Field(default=3, ge=1, le=3)

def _paper_execution_enabled() -> bool:
    return os.getenv("KIASHA_PAPER_EXECUTION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

def _auto_invest_runner_enabled() -> bool:
    return os.getenv("KIASHA_AUTO_INVEST_RUNNER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

def _agent_payload(agent: str) -> dict:
    stats = STORE.agent_stats(agent)
    if stats is None:
        return {"agent": agent,"evaluatedCalls": 0,"directionalAccuracy": None,"averageSignedReturn": None,"returnStd": None,"lastUpdated": None,"trustReady": False,"minimumObservedSamples": MIN_OBSERVED_SAMPLES}
    return {"agent": stats.agent,"evaluatedCalls": stats.evaluated_calls,"directionalAccuracy": stats.directional_accuracy,"averageSignedReturn": stats.average_realized_return,"returnStd": stats.return_std,"lastUpdated": stats.last_updated,"trustReady": stats.evaluated_calls >= MIN_OBSERVED_SAMPLES,"minimumObservedSamples": MIN_OBSERVED_SAMPLES}

def _server_paper_account(user_id: str) -> dict:
    return AUDIT_STORE.ensure_paper_account(user_id=str(user_id), initial_cash=DEFAULT_PAPER_INITIAL_CASH)

def _paper_sizing_capital(account: dict) -> float:
    invested_cost = sum(float(position["quantity"]) * float(position["avgCost"]) for position in account.get("positions", []))
    return float(account["cashBalance"]) + invested_cost

def _paper_symbol_position(account: dict, code: str) -> float:
    target = code.strip().upper()
    for position in account.get("positions", []):
        if str(position.get("code") or "").strip().upper() == target:
            return float(position.get("quantity") or 0)
    return 0.0

def _verified_reference_price(code: str) -> tuple[Optional[float], Optional[str]]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is None:
        return None, None
    candidate = getattr(quote, "last_price", None) or getattr(quote, "closing_price", None)
    if candidate is None or float(candidate) <= 0:
        return None, None
    return float(candidate), "verified-market-quote"

@router.get("/agents")
def performance_agents():
    items = [_agent_payload(agent) for agent in AGENTS]
    return {"items": items,"minimumObservedSamples": MIN_OBSERVED_SAMPLES,"observedTrustEnabledFor": [item["agent"] for item in items if item["trustReady"]]}

@router.get("/summary")
def performance_summary():
    pending = STORE.pending_observations(limit=5000)
    agents = [_agent_payload(agent) for agent in AGENTS]
    evaluated_counts = [item["evaluatedCalls"] for item in agents]
    return {"pendingRecommendations": len(pending),"evaluatedRecommendationsLowerBound": max(evaluated_counts, default=0),"minimumObservedSamples": MIN_OBSERVED_SAMPLES,"observedTrustActive": any(item["trustReady"] for item in agents),"agents": agents,"note": "evaluatedRecommendationsLowerBound is derived from agent observations; neutral votes may make per-agent counts differ."}

@router.get("/ai/status")
def ai_status():
    payload = kiasha_ai_status()
    payload["paperExecutionEnabled"] = _paper_execution_enabled()
    payload["runnerEnabled"] = _auto_invest_runner_enabled()
    payload["liveExecution"] = False
    return payload

@router.get("/ai/auto-invest")
def ai_auto_invest_status(user_id: str = Depends(require_user_id)):
    return auto_status(str(user_id))

@router.put("/ai/auto-invest")
def ai_auto_invest_update(req: AutoInvestSettingsRequest,user_id: str = Depends(require_user_id)):
    return update_auto_settings(str(user_id),enabled=req.enabled,horizon=req.horizon,max_daily_trades=req.maxDailyTrades)

@router.post("/ai/auto-invest/run-now")
def ai_auto_invest_run_now(user_id: str = Depends(require_user_id)):
    return run_user_auto_invest(str(user_id), force=True)

def _run_ai_analysis(code: str, horizon: Literal["short", "long"]):
    try:
        return analyze_with_ai(code, horizon=horizon)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI provider request failed") from exc

@router.post("/ai/analyze/{code}")
def ai_analyze(code: str,horizon: Literal["short", "long"] = Query(default="short"),_user_id: str = Depends(require_user_id)):
    proposal = _run_ai_analysis(code, horizon)
    return {"proposal": proposal.to_dict(),"paperExecution": False,"liveExecution": False,"requiresRiskCheckBeforeExecution": True}

@router.get("/ai/paper-account")
def ai_paper_account(user_id: str = Depends(require_user_id)):
    account = _server_paper_account(user_id)
    return {"account": account,"sizingCapital": _paper_sizing_capital(account),"serverOwned": True,"paperExecutionEnabled": _paper_execution_enabled(),"liveExecution": False}

@router.get("/ai/paper-decisions")
def ai_paper_decisions(limit: int = Query(default=50, ge=1, le=200),user_id: str = Depends(require_user_id)):
    return {"items": AUDIT_STORE.list_kiasha_ai_decisions(user_id=str(user_id), limit=limit),"paperExecutionEnabled": _paper_execution_enabled(),"liveExecution": False}

@router.post("/ai/paper-dry-run/{code}")
def ai_paper_dry_run(code: str,horizon: Literal["short", "long"] = Query(default="short"),user_id: str = Depends(require_user_id)):
    user_id = str(user_id)
    account = _server_paper_account(user_id)
    sizing_capital = _paper_sizing_capital(account)
    proposal = _run_ai_analysis(code, horizon)
    reference_price, reference_source = _verified_reference_price(code)
    result = evaluate_ai_paper_proposal(proposal,portfolio_value=sizing_capital,reference_price=reference_price,current_symbol_position=_paper_symbol_position(account, code),max_position_pct=5.0,execute=False)
    payload = result.to_dict()
    payload.update({"dryRun": True,"serverPaperSizingCapital": sizing_capital,"referencePrice": reference_price,"referencePriceSource": reference_source,"paperExecution": False,"liveExecution": False})
    decision_id = AUDIT_STORE.save_kiasha_ai_decision(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,result=payload,reference_price=reference_price,reference_source=reference_source,dry_run=True)
    payload["decisionId"] = decision_id
    return payload

@router.post("/ai/paper-execute/{code}")
def ai_paper_execute(code: str,horizon: Literal["short", "long"] = Query(default="short"),idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),user_id: str = Depends(require_user_id)):
    """Execute one guarded Paper BUY or ownership-bounded SELL. Never live."""
    if not _paper_execution_enabled():
        raise HTTPException(status_code=503, detail="Kiasha Paper execution is disabled")
    user_id = str(user_id)
    cached = AUDIT_STORE.get_idempotent_response(user_id=user_id, idempotency_key=idempotency_key)
    if cached is not None:
        return cached
    account = _server_paper_account(user_id)
    sizing_capital = _paper_sizing_capital(account)
    proposal = _run_ai_analysis(code, horizon)
    reference_price, reference_source = _verified_reference_price(code)
    owned = _paper_symbol_position(account, code)
    result = evaluate_ai_paper_proposal(proposal,portfolio_value=sizing_capital,reference_price=reference_price,current_symbol_position=owned,max_position_pct=5.0,execute=False)
    base_payload = result.to_dict()
    base_payload.update({"dryRun": False,"serverPaperSizingCapital": sizing_capital,"referencePrice": reference_price,"referencePriceSource": reference_source,"paperExecution": False,"liveExecution": False})
    if not result.allowed or result.intent is None or result.risk is None:
        decision_id = AUDIT_STORE.save_kiasha_ai_decision(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,result=base_payload,reference_price=reference_price,reference_source=reference_source,dry_run=False)
        base_payload["decisionId"] = decision_id
        return base_payload
    assert reference_price is not None and reference_source is not None
    side = str(result.intent.get("side"))
    notional = int(result.intent["quantity"]) * float(reference_price)
    if side == "BUY" and notional > float(account["cashBalance"]) + 1e-9:
        base_payload["allowed"] = False;base_payload["reasons"] = ["insufficient Paper cash balance"];base_payload["intent"] = None
        decision_id = AUDIT_STORE.save_kiasha_ai_decision(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,result=base_payload,reference_price=reference_price,reference_source=reference_source,dry_run=False)
        base_payload["decisionId"] = decision_id
        return base_payload
    if side == "SELL" and int(result.intent["quantity"]) > int(owned):
        raise HTTPException(status_code=409, detail="SELL quantity exceeds owned Paper position")
    receipt = submit_order_intent(result.intent)
    try:
        kwargs = dict(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,intent=result.intent,receipt=receipt,reference_price=reference_price,reference_source=reference_source,idempotency_key=idempotency_key)
        if side == "SELL":
            return PAPER_SELL_STORE.commit_sell_fill(**kwargs)
        return PAPER_EXECUTION_STORE.commit_buy_fill(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/market-symbols")
def market_symbols(market: Optional[str] = Query(default=None, description="TSE, IFB or IFB_BASE"),q: Optional[str] = Query(default=None, max_length=64),limit: int = Query(default=5000, ge=1, le=10000)):
    if market and market.upper() not in {"TSE", "IFB", "IFB_BASE"}:
        raise HTTPException(status_code=400, detail="market must be TSE, IFB or IFB_BASE")
    try:
        items = query_symbols(market=market, q=q, limit=limit)
    except SymbolUniverseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    sources = sorted({item.source for item in items})
    return {"count": len(items),"source": sources[0] if len(sources) == 1 else "mixed","sources": sources,"markets": ["TSE", "IFB", "IFB_BASE"],"degraded": bool(items) and all(item.source == "codal" for item in items),"items": [item.to_dict() for item in items]}
