"""Read-only performance routes plus guarded Kiasha Paper simulation APIs."""
import os
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from audit_store import AuditStore
from auth import require_user_id
from execution import submit_order_intent
from kiasha_ai import analyze as analyze_with_ai, status as kiasha_ai_status
from kiasha_auto_invest_v2 import auto_status, refresh_market_scan, run_user_auto_invest, scan_status, update_auto_settings
from kiasha_capital_mandate import STORE as KIASHA_CAPITAL_STORE
from kiasha_paper import evaluate_ai_paper_proposal
from manual_paper_routes import router as manual_paper_router
from market_data import MarketDataUnavailable, _read_json, _resolve_tsetmc_instrument_code, find_quote, tsetmc_api_base
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from risk import load_policy
from symbol_universe import SymbolUniverseUnavailable, query_symbols

router=APIRouter(prefix="/performance",tags=["performance"]); router.include_router(manual_paper_router)
STORE=PerformanceStore(); AUDIT_STORE=AuditStore(); PAPER_EXECUTION_STORE=PaperExecutionStore(); PAPER_SELL_STORE=PaperSellStore(); AGENTS=("fundamental","risk","forecast","comparison","technical","flow"); DEFAULT_PAPER_INITIAL_CASH=float(os.getenv("KIASHA_PAPER_INITIAL_CASH","100000000"))
class AutoInvestSettingsRequest(BaseModel):
    enabled: bool
    horizon: Literal["short","long"]="short"
    maxDailyTrades:int=Field(default=3,ge=1,le=3)
def _paper_execution_enabled(): return os.getenv("KIASHA_PAPER_EXECUTION_ENABLED","false").strip().lower() in {"1","true","yes","on"}
def _auto_invest_runner_enabled(): return os.getenv("KIASHA_AUTO_INVEST_RUNNER_ENABLED","false").strip().lower() in {"1","true","yes","on"}
def _agent_payload(agent):
    s=STORE.agent_stats(agent)
    if s is None:return {"agent":agent,"evaluatedCalls":0,"directionalAccuracy":None,"averageSignedReturn":None,"returnStd":None,"lastUpdated":None,"trustReady":False,"minimumObservedSamples":MIN_OBSERVED_SAMPLES}
    return {"agent":s.agent,"evaluatedCalls":s.evaluated_calls,"directionalAccuracy":s.directional_accuracy,"averageSignedReturn":s.average_realized_return,"returnStd":s.return_std,"lastUpdated":s.last_updated,"trustReady":s.evaluated_calls>=MIN_OBSERVED_SAMPLES,"minimumObservedSamples":MIN_OBSERVED_SAMPLES}
def _scan_agent_coverage(scan,agent): return sum(1 for item in scan.get("top10") or [] if any(isinstance(r,dict) and r.get("agent")==agent and float(r.get("confidence") or 0)>0 for r in (item.get("agentBreakdown") or [])))
def _server_paper_account(user_id): return AUDIT_STORE.ensure_paper_account(user_id=str(user_id),initial_cash=DEFAULT_PAPER_INITIAL_CASH)
def _paper_sizing_capital(account): return float(account["cashBalance"])+sum(float(p["quantity"])*float(p["avgCost"]) for p in account.get("positions",[]))
def _paper_symbol_position(account,code):
    target=code.strip().upper(); return next((float(p.get("quantity") or 0) for p in account.get("positions",[]) if str(p.get("code") or "").strip().upper()==target),0.0)
def _verified_reference_price(code):
    try:q=find_quote(code)
    except MarketDataUnavailable:q=None
    if q is None:return None,None,None
    c=getattr(q,"last_price",None) or getattr(q,"closing_price",None); return (float(c),"verified-market-quote",q.fetched_at) if c is not None and float(c)>0 else (None,None,None)
@router.get("/agents")
def performance_agents():
    items=[_agent_payload(a) for a in AGENTS]; return {"items":items,"minimumObservedSamples":MIN_OBSERVED_SAMPLES,"observedTrustEnabledFor":[x["agent"] for x in items if x["trustReady"]]}
@router.get("/summary")
def performance_summary():
    pending=STORE.pending_observations(limit=5000); agents=[_agent_payload(a) for a in AGENTS]; counts=[x["evaluatedCalls"] for x in agents]; return {"pendingRecommendations":len(pending),"evaluatedRecommendationsLowerBound":max(counts,default=0),"minimumObservedSamples":MIN_OBSERVED_SAMPLES,"observedTrustActive":any(x["trustReady"] for x in agents),"agents":agents,"note":"evaluatedRecommendationsLowerBound is derived from agent observations; neutral votes may make per-agent counts differ."}
@router.get("/kiasha-profile")
def kiasha_public_profile(): return {"capital":KIASHA_CAPITAL_STORE.aggregate_profile(),"liveExecution":False}
@router.get("/market-scan")
def market_scan(force:bool=Query(default=False)): return refresh_market_scan(force=force) if force else scan_status()
@router.get("/market-quote/{code}")
def market_quote(code:str):
    try:q=find_quote(code)
    except MarketDataUnavailable as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
    if q is None:raise HTTPException(status_code=404,detail=f"no verified market quote for {code}")
    return {"code":q.code,"name":q.name,"lastPrice":q.last_price,"closingPrice":q.closing_price,"yesterdayPrice":q.yesterday_price,"change":q.change,"changePercent":q.change_percent,"source":"verified-market-quote"}
@router.get("/market-history/{code}")
def market_history(code:str,days:int=Query(default=90,ge=5,le=400)):
    instrument_code=_resolve_tsetmc_instrument_code(code,timeout=12.0)
    if instrument_code is None:raise HTTPException(status_code=404,detail=f"could not resolve market instrument for {code}")
    try:payload=_read_json(f"{tsetmc_api_base()}/ClosingPrice/GetClosingPriceDailyList/{instrument_code}/{days}",timeout=12.0)
    except Exception as exc:raise HTTPException(status_code=503,detail="verified market history is temporarily unavailable") from exc
    rows=payload.get("closingPriceDaily")
    if not isinstance(rows,list):raise HTTPException(status_code=503,detail="market history response is invalid")
    points=[]
    for row in rows:
        if not isinstance(row,dict):continue
        try:close=float(row.get("pClosing") or row.get("pDrCotVal"))
        except (TypeError,ValueError):continue
        raw=row.get("dEven")
        if close>0 and raw not in(None,""):points.append({"date":str(raw),"close":close})
    points.sort(key=lambda x:x["date"]); return {"code":instrument_code,"count":len(points),"source":"tsetmc-history-via-biap","items":points}
@router.get("/readiness")
def kiasha_readiness():
    scan=scan_status();coverage=scan.get("deepDataCoverage") or {};agents=[_agent_payload(a) for a in AGENTS];tindex=bool(os.getenv("TINDEX_API_TOKEN"));ai=kiasha_ai_status();paper=_paper_execution_enabled();runner=_auto_invest_runner_enabled();tc=_scan_agent_coverage(scan,"technical");fc=_scan_agent_coverage(scan,"flow");pending=len(STORE.pending_observations(limit=5000));obs=any(x["trustReady"] for x in agents);tf=tc>0 and fc>0
    return {"chain":"kiasha-v2","marketScanReady":scan.get("status")=="OK" and bool(scan.get("top10")),"ordinaryEquityFilterReady":int(scan.get("ordinaryEquityCount") or 0)>0,"sharedTop10Ready":True,"paperExecutionReady":paper,"autoInvestRunnerReady":runner,"liveExecution":False,"sonnetFinalistGateReady":bool(ai.get("configured") or ai.get("enabled") or os.getenv("ANTHROPIC_API_KEY")),"technicalFlowSource":"tindex+tsetmc-fallback" if tindex else "tsetmc-history+client-type","technicalFlowReady":tf,"technicalFlowCoverage":{"technical":tc,"flow":fc,"top10":len(scan.get("top10") or [])},"technicalFlowBlocker":None if tf else "No verified technical/flow rows reached the cached Top 10 yet; refresh the market scan after deployment.","tindexConfigured":tindex,"tindexCoverage":int(coverage.get("tindex") or 0),"codalCoverage":int(coverage.get("codal") or 0),"codalDiagnostics":scan.get("codalDiagnostics") or [],"marketExtendedCoverage":int(coverage.get("marketExtended") or 0),"observedTrustActive":obs,"observedTrustState":"active" if obs else "learning","pendingObservations":pending,"minimumObservedSamples":MIN_OBSERVED_SAMPLES,"agents":agents,"scan":{"createdAt":scan.get("createdAt"),"deepAnalyzedCount":scan.get("deepAnalyzedCount"),"top10Count":len(scan.get("top10") or [])}}
@router.get("/ai/status")
def ai_status():
    p=kiasha_ai_status();p["paperExecutionEnabled"]=_paper_execution_enabled();p["runnerEnabled"]=_auto_invest_runner_enabled();p["liveExecution"]=False;return p
@router.get("/ai/auto-invest")
def ai_auto_invest_status(user_id:str=Depends(require_user_id)):return auto_status(str(user_id))
@router.put("/ai/auto-invest")
def ai_auto_invest_update(req:AutoInvestSettingsRequest,user_id:str=Depends(require_user_id)):return update_auto_settings(str(user_id),enabled=req.enabled,horizon=req.horizon,max_daily_trades=req.maxDailyTrades)
@router.post("/ai/auto-invest/run-now")
def ai_auto_invest_run_now(user_id:str=Depends(require_user_id)):return run_user_auto_invest(str(user_id),force=True)
def _run_ai_analysis(code,horizon):
    try:return analyze_with_ai(code,horizon=horizon)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
    except RuntimeError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(status_code=502,detail="AI provider request failed") from exc
@router.post("/ai/analyze/{code}")
def ai_analyze(code:str,horizon:Literal["short","long"]=Query(default="short"),_user_id:str=Depends(require_user_id)):return {"proposal":_run_ai_analysis(code,horizon).to_dict(),"paperExecution":False,"liveExecution":False,"requiresRiskCheckBeforeExecution":True}
@router.get("/ai/paper-account")
def ai_paper_account(user_id:str=Depends(require_user_id)):
    account=_server_paper_account(user_id);policy=load_policy();loss=PAPER_EXECUTION_STORE.daily_realized_loss_used(user_id=str(user_id));mandate=KIASHA_CAPITAL_STORE.active_mandate(user_id=str(user_id));available=KIASHA_CAPITAL_STORE.manual_available_cash(user_id=str(user_id),paper_cash_balance=float(account["cashBalance"])); return {"account":account,"sizingCapital":_paper_sizing_capital(account),"manualAvailableCash":available,"kiashaCapitalMandate":mandate,"serverOwned":True,"paperExecutionEnabled":_paper_execution_enabled(),"liveExecution":False,"dailyRealizedLoss":{"used":loss,"limit":policy.max_daily_realized_loss,"buysPaused":loss>=policy.max_daily_realized_loss}}
@router.get("/ai/paper-equity-history")
def ai_paper_equity_history(limit:int=Query(default=400,ge=1,le=2000),user_id:str=Depends(require_user_id)):
    items=AUDIT_STORE.list_paper_equity_snapshots(user_id=str(user_id),limit=limit);return {"items":items,"count":len(items)}
@router.get("/ai/paper-decisions")
def ai_paper_decisions(limit:int=Query(default=50,ge=1,le=200),user_id:str=Depends(require_user_id)):return {"items":AUDIT_STORE.list_kiasha_ai_decisions(user_id=str(user_id),limit=limit),"paperExecutionEnabled":_paper_execution_enabled(),"liveExecution":False}
@router.post("/ai/paper-dry-run/{code}")
def ai_paper_dry_run(code:str,horizon:Literal["short","long"]=Query(default="short"),user_id:str=Depends(require_user_id)):
    user_id=str(user_id);account=_server_paper_account(user_id);mandate=KIASHA_CAPITAL_STORE.active_mandate(user_id=user_id);sizing=float(mandate["accountingEquityAtCost"]) if mandate else 0.0;proposal=_run_ai_analysis(code,horizon);price,source,fetched=_verified_reference_price(code);owned=next((float(p["quantity"]) for p in (mandate or {}).get("positions",[]) if p["code"].upper()==code.upper()),0.0);result=evaluate_ai_paper_proposal(proposal,portfolio_value=sizing,reference_price=price,current_symbol_position=owned,max_position_pct=5.0,quote_fetched_at=fetched,execute=False);payload=result.to_dict();payload.update({"dryRun":True,"kiashaMandateSizingCapital":sizing,"referencePrice":price,"referencePriceSource":source,"paperExecution":False,"liveExecution":False,"requiresCapitalMandate":mandate is None});decision_id=AUDIT_STORE.save_kiasha_ai_decision(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,result=payload,reference_price=price,reference_source=source,dry_run=True);payload["decisionId"]=decision_id;return payload
@router.post("/ai/paper-execute/{code}")
def ai_paper_execute(code:str,horizon:Literal["short","long"]=Query(default="short"),idempotency_key:str=Header(...,alias="Idempotency-Key",min_length=8,max_length=128),user_id:str=Depends(require_user_id)):
    if not _paper_execution_enabled():raise HTTPException(status_code=503,detail="Kiasha Paper execution is disabled")
    user_id=str(user_id);cached=AUDIT_STORE.get_idempotent_response(user_id=user_id,idempotency_key=idempotency_key)
    if cached is not None:return cached
    account=_server_paper_account(user_id);mandate=KIASHA_CAPITAL_STORE.active_mandate(user_id=user_id)
    if mandate is None:raise HTTPException(status_code=409,detail="Create a Kiasha capital mandate before Kiasha Paper execution")
    sizing=float(mandate["accountingEquityAtCost"]);proposal=_run_ai_analysis(code,horizon);price,source,fetched=_verified_reference_price(code);owned=next((float(p["quantity"]) for p in mandate.get("positions",[]) if p["code"].upper()==code.upper()),0.0);result=evaluate_ai_paper_proposal(proposal,portfolio_value=sizing,reference_price=price,current_symbol_position=owned,max_position_pct=5.0,quote_fetched_at=fetched,execute=False);base=result.to_dict();base.update({"dryRun":False,"kiashaMandateSizingCapital":sizing,"referencePrice":price,"referencePriceSource":source,"paperExecution":False,"liveExecution":False})
    if not result.allowed or result.intent is None or result.risk is None:
        decision_id=AUDIT_STORE.save_kiasha_ai_decision(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,result=base,reference_price=price,reference_source=source,dry_run=False);base["decisionId"]=decision_id;return base
    assert price is not None and source is not None;side=str(result.intent.get("side"));notional=int(result.intent["quantity"])*float(price)
    if side=="BUY" and notional>float(mandate["mandateCash"])+1e-9:raise HTTPException(status_code=409,detail="Kiasha BUY exceeds remaining mandate cash")
    if side=="SELL" and int(result.intent["quantity"])>int(owned):raise HTTPException(status_code=409,detail="Kiasha SELL exceeds mandate-owned position")
    receipt=submit_order_intent(result.intent);kwargs=dict(user_id=user_id,code=code,horizon=horizon,proposal=proposal.to_dict(),risk=result.risk,intent=result.intent,receipt=receipt,reference_price=price,reference_source=source,idempotency_key=idempotency_key)
    try:return PAPER_SELL_STORE.commit_sell_fill(**kwargs) if side=="SELL" else PAPER_EXECUTION_STORE.commit_buy_fill(**kwargs)
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
@router.get("/market-symbols")
def market_symbols(market:Optional[str]=Query(default=None),q:Optional[str]=Query(default=None,max_length=64),limit:int=Query(default=5000,ge=1,le=10000)):
    if market and market.upper() not in {"TSE","IFB","IFB_BASE"}:raise HTTPException(status_code=400,detail="market must be TSE, IFB or IFB_BASE")
    try:items=query_symbols(market=market,q=q,limit=limit)
    except SymbolUniverseUnavailable as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
    sources=sorted({item.source for item in items});return {"count":len(items),"source":sources[0] if len(sources)==1 else "mixed","sources":sources,"markets":["TSE","IFB","IFB_BASE"],"degraded":bool(items) and all(item.source=="codal" for item in items),"items":[item.to_dict() for item in items]}

from kiasha_capital_routes import router as capital_router
router.include_router(capital_router)
