"""
Minimal HTTP wrapper around the Kiasha decision and guarded execution layers.

Additive endpoints intended to sit alongside the existing BIAP backend:

  GET  /stock/recommendation/{code}
  POST /orders/preview
  POST /orders/submit

Execution is intentionally limited to PAPER and APPROVAL flows. AUTO/LIVE
execution is blocked until a real broker adapter, credentials, compliance
review, and production risk controls exist.

Currently backed by MOCK_COMPANIES only (see data_sample.py) — CODAL/TSETMC
ingestion is not wired in yet (see PROJECT_STATUS.md, "Open blockers").

Run locally:
    pip install -r requirements.txt
    uvicorn api_server:app --reload --port 8088
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from data_sample import SAMPLE_COMPANY
from execution import ExecutionPolicyError, build_order_intent, submit_order_intent
from kiasha import decide

app = FastAPI(title="BIAP Kiasha recommendation service")

# Keyed by ticker. Only one mock entry until real CODAL/TSETMC ingestion
# replaces this with a live lookup.
MOCK_COMPANIES = {SAMPLE_COMPANY["ticker"]: SAMPLE_COMPANY}

# Ephemeral in-memory intents for the prototype only. Production must use a
# persistent audit store with authenticated user/account ownership.
ORDER_INTENTS: dict[str, dict] = {}


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
        "mode": "mock",
        "companies": list(MOCK_COMPANIES),
        "execution": {
            "paper": True,
            "approval": True,
            "auto": False,
            "brokerConnected": False,
        },
    }


def _company_or_404(code: str):
    company = MOCK_COMPANIES.get(code.upper())
    if company is None:
        raise HTTPException(status_code=404, detail=f"no data for {code}")
    return company


@app.get("/stock/recommendation/{code}")
def recommendation(code: str):
    company = _company_or_404(code)
    decision = decide(company)
    return {
        "code": company["ticker"],
        "call": decision.call,
        "score": decision.weighted_score,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "breakdown": decision.breakdown,
    }


@app.post("/orders/preview")
def preview_order(req: OrderPreviewRequest):
    company = _company_or_404(req.code)
    decision = decide(company)
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ORDER_INTENTS[intent["id"]] = intent
    return {
        "intent": intent,
        "recommendation": {
            "call": decision.call,
            "score": decision.weighted_score,
        },
        "liveExecution": False,
    }


@app.post("/orders/submit")
def submit_order(req: OrderSubmitRequest):
    intent = ORDER_INTENTS.get(req.intentId)
    if intent is None:
        raise HTTPException(status_code=404, detail="unknown intentId")
    try:
        receipt = submit_order_intent(intent)
    except ExecutionPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ORDER_INTENTS[req.intentId] = receipt
    return receipt
