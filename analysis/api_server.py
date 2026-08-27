"""HTTP wrapper around the Kiasha decision and guarded execution layers."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional
import asyncio
import os
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from admin_auth import AdminAuthRequired
from admin_routes import router as admin_router
from audit_store import AuditStore
from auth import require_approver, require_user_id
from codal_data import base_url as codal_base_url
from company_builder import availability, build_company_from_quote, build_company_from_symbol
from data_sample import SAMPLE_COMPANY
from execution import (
    ExecutionPolicyError,
    approve_order_intent,
    build_order_intent,
    reject_order_intent,
    submit_order_intent,
)
from kiasha import decide
from market_data import MarketDataUnavailable, base_url as market_base_url, find_quote
from performance_routes import router as performance_router
from risk import evaluate_order_risk, policy_snapshot
from symbol_universe import SymbolUniverseUnavailable, query_symbols


_WARMUP = {"ready": True, "running": False, "symbols": [], "error": None}


def _configured_warm_symbols() -> list[str]:
    """Return explicitly configured symbols to preload before serving recommendations."""
    raw = os.getenv("BIAP_WARM_SYMBOLS", "")
    seen: set[str] = set()
    result: list[str] = []
    for part in raw.split(","):
        symbol = part.strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _warm_symbol(symbol: str) -> None:
    """Populate the same verified caches used by a real recommendation request."""
    _company_or_404(symbol)


async def _run_warmup(symbols: list[str]) -> None:
    _WARMUP.update({"ready": False, "running": True, "symbols": symbols, "error": None})
    try:
        results = await asyncio.gather(
            *(asyncio.to_thread(_warm_symbol, symbol) for symbol in symbols),
            return_exceptions=True,
        )
        failures = [str(result) for result in results if isinstance(result, Exception)]
        if failures:
            _WARMUP["error"] = "; ".join(failures[:3])
    finally:
        # Warm-up is best-effort: once it finishes, normal requests may proceed
        # and can still use verified degraded fallbacks if a source was unavailable.
        _WARMUP["running"] = False
        _WARMUP["ready"] = True


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    symbols = _configured_warm_symbols()
    task = None
    if symbols:
        # Start serving health/readiness immediately while caches warm in the
        # background. Recommendation endpoints reject with 503 until warm-up
        # completes, so users never sit on a 30+ second cold request.
        _WARMUP.update({"ready": False, "running": True, "symbols": symbols, "error": None})
        task = asyncio.create_task(_run_warmup(symbols))
    else:
        _WARMUP.update({"ready": True, "running": False, "symbols": [], "error": None})
    yield
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="BIAP Kiasha recommendation service", lifespan=_lifespan)
app.include_router(performance_router)
app.include_router(admin_router)


@app.exception_handler(AdminAuthRequired)
def _admin_auth_required(_request: Request, _exc: AdminAuthRequired) -> RedirectResponse:
    return RedirectResponse("/admindir/login", status_code=303)

MOCK_COMPANIES = {SAMPLE_COMPANY["ticker"]: SAMPLE_COMPANY}
AUDIT = AuditStore()


class OrderPreviewRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    limitPrice: Optional[float] = Field(default=None, gt=0)
    mode: Literal["paper", "approval", "auto"] = "paper"


class OrderSubmitRequest(BaseModel):
    intentId: str = Field(min_length=1)


class OrderRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


def _require_warm_ready() -> None:
    if not _WARMUP["ready"]:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "service warming caches",
                "retryable": True,
                "warmup": dict(_WARMUP),
            },
        )


@app.get("/health")
def health():
    return {
        "status": "ok" if _WARMUP["ready"] else "warming",
        "ready": bool(_WARMUP["ready"]),
        "warmup": dict(_WARMUP),
        "mode": "mock+live",
        "mockCompanies": list(MOCK_COMPANIES),
        "liveMarketData": {
            "base": market_base_url(),
            "fields": ["lastPrice", "closingPrice", "yesterdayPrice", "change", "changePercent"],
            "extendedMarketDataConnected": False,
        },
        "symbolUniverse": {
            "preferredSource": "tsetmc",
            "fallbackSource": "codal",
            "markets": ["TSE", "IFB", "IFB_BASE"],
            "watchlistIndependent": True,
            "degradedModeSupported": True,
        },
        "codal": {
            "base": codal_base_url(),
            "metadataConnected": True,
            "fundamentalsConnected": True,
        },
        "execution": {
            "paper": True,
            "approval": True,
            "auto": False,
            "brokerConnected": False,
            "persistentAudit": True,
            "riskPolicy": True,
            "ownershipEnforced": True,
            "authenticationVerified": bool(os.environ.get("BIAP_AUTH_JWT_SECRET")),
            "idempotencySupported": True,
        },
    }


def _company_or_404(code: str) -> tuple[dict, str]:
    mock = MOCK_COMPANIES.get(code.upper())
    if mock is not None:
        return mock, "mock"

    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is not None:
        # `code` here is whatever matched find_quote's numeric TSETMC id -- CODAL
        # indexes issuers by their Persian ticker, so enrichment must use
        # quote.name, not the raw path code (see analysis/PROJECT_STATUS.md).
        return build_company_from_quote(quote, codal_symbol=quote.name), "live"

    # TSETMC can be unreachable from some VPS networks. In that case a Persian
    # issuer symbol may still be resolved and analyzed from verified CODAL
    # filings. No price/market values are synthesized in this degraded mode.
    company = build_company_from_symbol(code)
    if company is not None:
        return company, "codal"

    raise HTTPException(status_code=404, detail=f"no data for {code}")


def _reference_price(company: dict) -> Optional[float]:
    raw = company.get("market", {}).get("price")
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


@app.get("/stock/symbols")
def symbols(
    market: Optional[str] = Query(default=None, description="TSE, IFB or IFB_BASE"),
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=5000, ge=1, le=10000),
):
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


@app.get("/stock/recommendation/{code}")
def recommendation(code: str):
    _require_warm_ready()
    company, source = _company_or_404(code)
    decision = decide(company)
    market = company.get("market") or {}
    return {
        "code": company["ticker"],
        "name": company.get("name_fa"),
        "call": decision.call,
        "score": decision.weighted_score,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataSource": source,
        "dataAvailability": availability(company),
        "codalMetadata": company.get("codal_metadata") if source in {"live", "codal"} else None,
        "codalFundamentals": company.get("codal") if source in {"live", "codal"} else None,
        "livePrice": {
            "lastPrice": market.get("last_price"),
            "closingPrice": market.get("closing_price"),
            "yesterdayPrice": market.get("yesterday_price"),
            "changePercent": market.get("change_percent"),
        } if source == "live" else None,
        "extendedMarket": {
            "dayLow": market.get("day_low"),
            "dayHigh": market.get("day_high"),
            "volumeToday": market.get("volume_today"),
            "tradeValueToday": market.get("trade_value_today"),
            "tradeCountToday": market.get("trade_count_today"),
            "avgVolume30d": market.get("avg_volume_30d"),
            "price52wHigh": market.get("price_52w_high"),
            "price52wLow": market.get("price_52w_low"),
            "pe": market.get("pe"),
            "sectorAvgPe": market.get("sector_avg_pe"),
            "epsValue": market.get("eps_value"),
            "estimatedEps": market.get("estimated_eps"),
            "marketCap": market.get("market_cap"),
            "marketCapBn": market.get("market_cap_bn"),
            "sharesOutstanding": market.get("shares_outstanding"),
            "sectorName": market.get("sector_name"),
        } if source == "live" else None,
        "breakdown": decision.breakdown,
    }


@app.get("/risk/status")
def risk_status():
    return {
        "policy": policy_snapshot(),
        "dailyNotionalUsed": AUDIT.submitted_notional_today(),
        "autoExecutionEnabled": False,
    }


@app.post("/orders/preview")
def preview_order(
    req: OrderPreviewRequest,
    user_id: str = Depends(require_user_id),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    _require_warm_ready()
    if idempotency_key:
        cached = AUDIT.get_idempotent_response(user_id=user_id, idempotency_key=idempotency_key)
        if cached is not None:
            return cached

    company, _source = _company_or_404(req.code)
    decision = decide(company)
    reference_price = _reference_price(company)

    risk = evaluate_order_risk(
        side=req.side,
        quantity=req.quantity,
        limit_price=req.limitPrice,
        reference_price=reference_price,
        recommendation_score=decision.weighted_score,
        daily_notional_used=AUDIT.submitted_notional_today(),
        current_symbol_position=AUDIT.symbol_net_position_today(company["ticker"]),
    )

    if not risk.allowed:
        AUDIT.record_event(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            event_type="RISK_REJECTED",
            payload={
                "code": company["ticker"],
                "side": req.side,
                "quantity": req.quantity,
                "limitPrice": req.limitPrice,
                "mode": req.mode,
                "recommendation": {"call": decision.call, "score": decision.weighted_score},
                "referencePrice": reference_price,
                "risk": risk.to_dict(),
            },
        )
        raise HTTPException(
            status_code=400,
            detail={"message": "order rejected by risk policy", "risk": risk.to_dict()},
        )

    try:
        intent = build_order_intent(
            code=company["ticker"],
            side=req.side,
            quantity=req.quantity,
            limit_price=req.limitPrice,
            mode=req.mode,
            recommendation_call=decision.call,
            recommendation_score=decision.weighted_score,
        )
    except ExecutionPolicyError as exc:
        AUDIT.record_event(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            intent_id=None,
            event_type="EXECUTION_POLICY_REJECTED",
            payload={
                "code": company["ticker"],
                "side": req.side,
                "quantity": req.quantity,
                "limitPrice": req.limitPrice,
                "mode": req.mode,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    intent["risk"] = risk.to_dict()
    intent["referencePrice"] = reference_price
    AUDIT.save_intent(intent, user_id=user_id)
    AUDIT.record_event(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        intent_id=intent["id"],
        event_type="INTENT_CREATED",
        payload={"intent": intent},
    )

    response = {
        "intent": intent,
        "recommendation": {"call": decision.call, "score": decision.weighted_score},
        "risk": risk.to_dict(),
        "liveExecution": False,
    }
    if idempotency_key:
        AUDIT.save_idempotent_response(
            user_id=user_id, idempotency_key=idempotency_key, intent_id=intent["id"], response=response
        )
    return response


@app.post("/orders/submit")
def submit_order(req: OrderSubmitRequest, user_id: str = Depends(require_user_id)):
    intent = AUDIT.get_intent(req.intentId, user_id=user_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="unknown intentId")

    if intent["status"] in {"PAPER_FILLED", "PENDING_APPROVAL"}:
        # Already submitted: return the existing state instead of re-simulating
        # a fill or re-creating a pending-approval event for the same intent.
        return intent

    try:
        receipt = submit_order_intent(intent)
    except ExecutionPolicyError as exc:
        AUDIT.record_event(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            intent_id=req.intentId,
            event_type="SUBMIT_REJECTED",
            payload={"error": str(exc), "intent": intent},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    AUDIT.save_intent(receipt, user_id=user_id)
    AUDIT.record_event(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        intent_id=req.intentId,
        event_type="ORDER_SUBMITTED",
        payload={"receipt": receipt},
    )
    return receipt


@app.get("/orders/{intent_id}")
def get_order(intent_id: str, user_id: str = Depends(require_user_id)):
    intent = AUDIT.get_intent(intent_id, user_id=user_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="unknown intentId")
    return intent


def _resolve_approval(intent_id: str, *, event_type: str, transition, payload_extra: dict):
    found = AUDIT.get_intent_any_owner(intent_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown intentId")
    owner_user_id, intent = found

    try:
        resolved = transition(intent)
    except ExecutionPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    AUDIT.save_intent(resolved, user_id=owner_user_id)
    AUDIT.record_event(
        event_id=str(uuid.uuid4()),
        user_id=owner_user_id,
        intent_id=intent_id,
        event_type=event_type,
        payload={"actor": "approver", "intent": resolved, **payload_extra},
    )
    return resolved


@app.post("/orders/{intent_id}/approve")
def approve_order(intent_id: str, _approver: None = Depends(require_approver)):
    return _resolve_approval(
        intent_id, event_type="ORDER_APPROVED", transition=approve_order_intent, payload_extra={}
    )


@app.post("/orders/{intent_id}/reject")
def reject_order(
    intent_id: str,
    req: OrderRejectRequest = OrderRejectRequest(),
    _approver: None = Depends(require_approver),
):
    return _resolve_approval(
        intent_id,
        event_type="ORDER_REJECTED",
        transition=lambda intent: reject_order_intent(intent, reason=req.reason),
        payload_extra={"reason": req.reason},
    )


@app.get("/audit/orders")
def audit_orders(limit: int = Query(default=100, ge=1, le=500), user_id: str = Depends(require_user_id)):
    return {"items": AUDIT.list_intents(user_id=user_id, limit=limit)}


@app.get("/audit/events")
def audit_events(limit: int = Query(default=200, ge=1, le=1000), user_id: str = Depends(require_user_id)):
    return {"items": AUDIT.list_events(user_id=user_id, limit=limit)}
