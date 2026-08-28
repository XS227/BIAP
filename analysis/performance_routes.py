"""Read-only API routes for real Kiasha/agent performance observations."""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from audit_store import AuditStore
from auth import require_user_id
from kiasha_ai import analyze as analyze_with_ai, status as kiasha_ai_status
from kiasha_paper import evaluate_ai_paper_proposal
from market_data import MarketDataUnavailable, find_quote
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from symbol_universe import SymbolUniverseUnavailable, query_symbols


router = APIRouter(prefix="/performance", tags=["performance"])
STORE = PerformanceStore()
AUDIT_STORE = AuditStore()
AGENTS = ("fundamental", "risk", "forecast", "comparison")
DEFAULT_PAPER_INITIAL_CASH = float(os.getenv("KIASHA_PAPER_INITIAL_CASH", "100000000"))


def _agent_payload(agent: str) -> dict:
    stats = STORE.agent_stats(agent)
    if stats is None:
        return {
            "agent": agent,
            "evaluatedCalls": 0,
            "directionalAccuracy": None,
            "averageSignedReturn": None,
            "returnStd": None,
            "lastUpdated": None,
            "trustReady": False,
            "minimumObservedSamples": MIN_OBSERVED_SAMPLES,
        }
    return {
        "agent": stats.agent,
        "evaluatedCalls": stats.evaluated_calls,
        "directionalAccuracy": stats.directional_accuracy,
        "averageSignedReturn": stats.average_realized_return,
        "returnStd": stats.return_std,
        "lastUpdated": stats.last_updated,
        "trustReady": stats.evaluated_calls >= MIN_OBSERVED_SAMPLES,
        "minimumObservedSamples": MIN_OBSERVED_SAMPLES,
    }


def _server_paper_account(user_id: str) -> dict:
    return AUDIT_STORE.ensure_paper_account(
        user_id=str(user_id),
        initial_cash=DEFAULT_PAPER_INITIAL_CASH,
    )


def _paper_sizing_capital(account: dict) -> float:
    """Server-owned sizing base. Positions use persisted cost basis, never client input."""
    invested_cost = sum(
        float(position["quantity"]) * float(position["avgCost"])
        for position in account.get("positions", [])
    )
    return float(account["cashBalance"]) + invested_cost


def _paper_symbol_position(account: dict, code: str) -> float:
    target = code.strip().upper()
    for position in account.get("positions", []):
        if str(position.get("code") or "").strip().upper() == target:
            return float(position.get("quantity") or 0)
    return 0.0


@router.get("/agents")
def performance_agents():
    items = [_agent_payload(agent) for agent in AGENTS]
    return {
        "items": items,
        "minimumObservedSamples": MIN_OBSERVED_SAMPLES,
        "observedTrustEnabledFor": [item["agent"] for item in items if item["trustReady"]],
    }


@router.get("/summary")
def performance_summary():
    pending = STORE.pending_observations(limit=5000)
    agents = [_agent_payload(agent) for agent in AGENTS]
    evaluated_counts = [item["evaluatedCalls"] for item in agents]
    return {
        "pendingRecommendations": len(pending),
        "evaluatedRecommendationsLowerBound": max(evaluated_counts, default=0),
        "minimumObservedSamples": MIN_OBSERVED_SAMPLES,
        "observedTrustActive": any(item["trustReady"] for item in agents),
        "agents": agents,
        "note": "evaluatedRecommendationsLowerBound is derived from agent observations; neutral votes may make per-agent counts differ.",
    }


@router.get("/ai/status")
def ai_status():
    """Safe public readiness only; never returns the API key."""
    return kiasha_ai_status()


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
def ai_analyze(
    code: str,
    horizon: Literal["short", "long"] = Query(default="short"),
    _user_id: str = Depends(require_user_id),
):
    """Run the paid Claude brain in proposal-only mode."""
    proposal = _run_ai_analysis(code, horizon)
    return {
        "proposal": proposal.to_dict(),
        "paperExecution": False,
        "liveExecution": False,
        "requiresRiskCheckBeforeExecution": True,
    }


@router.get("/ai/paper-account")
def ai_paper_account(user_id: str = Depends(require_user_id)):
    """Return server-owned Paper capital/positions; no mutation or execution."""
    account = _server_paper_account(user_id)
    return {
        "account": account,
        "sizingCapital": _paper_sizing_capital(account),
        "serverOwned": True,
        "paperExecutionEnabled": False,
        "liveExecution": False,
    }


@router.get("/ai/paper-decisions")
def ai_paper_decisions(
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(require_user_id),
):
    """Authenticated immutable decision history for the current user."""
    return {
        "items": AUDIT_STORE.list_kiasha_ai_decisions(user_id=str(user_id), limit=limit),
        "paperExecutionEnabled": False,
        "liveExecution": False,
    }


@router.post("/ai/paper-dry-run/{code}")
def ai_paper_dry_run(
    code: str,
    horizon: Literal["short", "long"] = Query(default="short"),
    user_id: str = Depends(require_user_id),
):
    """Run Claude then deterministic Paper risk checks without any fill.

    Sizing comes exclusively from the authenticated user's server-owned Paper
    account. Client-supplied balances are not accepted. The gate is always
    called with execute=False, so neither PaperBroker nor a live broker can fill.
    Every resulting proposal/risk decision is persisted before returning.
    """
    user_id = str(user_id)
    account = _server_paper_account(user_id)
    sizing_capital = _paper_sizing_capital(account)
    proposal = _run_ai_analysis(code, horizon)

    reference_price = None
    reference_source = None
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is not None:
        candidate = getattr(quote, "last_price", None) or getattr(quote, "closing_price", None)
        if candidate is not None and float(candidate) > 0:
            reference_price = float(candidate)
            reference_source = "verified-market-quote"

    result = evaluate_ai_paper_proposal(
        proposal,
        portfolio_value=sizing_capital,
        reference_price=reference_price,
        current_symbol_position=_paper_symbol_position(account, code),
        execute=False,
    )
    payload = result.to_dict()
    payload.update({
        "dryRun": True,
        "serverPaperSizingCapital": sizing_capital,
        "referencePrice": reference_price,
        "referencePriceSource": reference_source,
        "paperExecution": False,
        "liveExecution": False,
    })
    decision_id = AUDIT_STORE.save_kiasha_ai_decision(
        user_id=user_id,
        code=code,
        horizon=horizon,
        proposal=proposal.to_dict(),
        risk=result.risk,
        result=payload,
        reference_price=reference_price,
        reference_source=reference_source,
        dry_run=True,
    )
    payload["decisionId"] = decision_id
    return payload


@router.get("/market-symbols")
def market_symbols(
    market: Optional[str] = Query(default=None, description="TSE, IFB or IFB_BASE"),
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=5000, ge=1, le=10000),
):
    """Compatibility route for mobile full-market discovery.

    `/api/performance/*` is already routed by production nginx to biap-fin,
    while generic `/api/stock/symbols` may still fall through to the legacy
    Express backend during migration. Keep the canonical `/stock/symbols`
    route in api_server.py; this alias lets mobile work before nginx cutover.
    """
    if market and market.upper() not in {"TSE", "IFB", "IFB_BASE"}:
        raise HTTPException(status_code=400, detail="market must be TSE, IFB or IFB_BASE")
    try:
        items = query_symbols(market=market, q=q, limit=limit)
    except SymbolUniverseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    sources = sorted({item.source for item in items})
    return {
        "count": len(items),
        "source": sources[0] if len(sources) == 1 else "mixed",
        "sources": sources,
        "markets": ["TSE", "IFB", "IFB_BASE"],
        "degraded": bool(items) and all(item.source == "codal" for item in items),
        "items": [item.to_dict() for item in items],
    }
