"""Read-only API routes for real Kiasha/agent performance observations."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_user_id
from kiasha_ai import analyze as analyze_with_ai, status as kiasha_ai_status
from kiasha_paper import evaluate_ai_paper_proposal
from market_data import MarketDataUnavailable, find_quote
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from symbol_universe import SymbolUniverseUnavailable, query_symbols


router = APIRouter(prefix="/performance", tags=["performance"])
STORE = PerformanceStore()
AGENTS = ("fundamental", "risk", "forecast", "comparison")


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


@router.post("/ai/paper-dry-run/{code}")
def ai_paper_dry_run(
    code: str,
    horizon: Literal["short", "long"] = Query(default="short"),
    portfolio_value: float = Query(default=100_000_000.0, gt=0, le=100_000_000_000_000.0),
    _user_id: str = Depends(require_user_id),
):
    """Run Claude then the deterministic Paper risk gate without any fill.

    ``portfolio_value`` is hypothetical sizing input for this dry-run endpoint;
    it is not treated as a verified brokerage balance. The function always calls
    the gate with ``execute=False``, so neither PaperBroker nor any live broker
    receives an order.
    """
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
        portfolio_value=portfolio_value,
        reference_price=reference_price,
        execute=False,
    )
    payload = result.to_dict()
    payload.update({
        "dryRun": True,
        "hypotheticalPortfolioValue": portfolio_value,
        "referencePrice": reference_price,
        "referencePriceSource": reference_source,
        "paperExecution": False,
        "liveExecution": False,
    })
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
