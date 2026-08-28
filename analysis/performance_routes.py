"""Read-only API routes for real Kiasha/agent performance observations."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
