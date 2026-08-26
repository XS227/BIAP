"""HTTP wrapper around the Kiasha decision and guarded execution layers."""

from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from audit_store import AuditStore
from auth import require_user_id
from codal_data import base_url as codal_base_url
from company_builder import availability, build_company_from_quote, build_company_from_symbol
from data_sample import SAMPLE_COMPANY
from execution import ExecutionPolicyError, build_order_intent, submit_order_intent
from kiasha import decide
from market_data import MarketDataUnavailable, base_url as market_base_url, find_quote
from risk import evaluate_order_risk, policy_snapshot
from symbol_universe import SymbolUniverseUnavailable, query_symbols

app = FastAPI(title="BIAP Kiasha recommendation service")

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


@app.get("/health")
def health():
    return {
        "status": "ok",
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
            "authenticationVerified": False,
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
        return build_company_from_quote(quote, codal_symbol=code), "live"

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


@app.get("/audit/orders")
def audit_orders(limit: int = Query(default=100, ge=1, le=500), user_id: str = Depends(require_user_id)):
    return {"items": AUDIT.list_intents(user_id=user_id, limit=limit)}


@app.get("/audit/events")
def audit_events(limit: int = Query(default=200, ge=1, le=1000), user_id: str = Depends(require_user_id)):
    return {"items": AUDIT.list_events(user_id=user_id, limit=limit)}
