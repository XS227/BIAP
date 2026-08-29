"""Manual Paper execution for the recommendation currently shown in mobile.

Unlike the autonomous/Claude path, this route does not ask Claude to analyze the
same symbol a second time. It recomputes BIAP's deterministic Kiasha team signal
from verified server data and, when that signal still matches the requested
side, submits a small Paper-only order through the same risk and atomic ledger
stores. This keeps the button responsive and avoids a second AI result
contradicting the recommendation the user is looking at.
"""

from __future__ import annotations

from dataclasses import replace
import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from audit_store import AuditStore
from auth import require_user_id
from company_builder import build_company_from_quote, build_company_from_symbol
from execution import build_order_intent, submit_order_intent
from kiasha import decide
from market_data import MarketDataUnavailable, find_quote
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore
from risk import evaluate_order_risk, load_policy


router = APIRouter(prefix="/ai", tags=["performance"])
AUDIT = AuditStore()
BUY_STORE = PaperExecutionStore()
SELL_STORE = PaperSellStore()
DEFAULT_PAPER_INITIAL_CASH = float(os.getenv("KIASHA_PAPER_INITIAL_CASH", "100000000"))


class ManualPaperOrderRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    quantity: int = Field(default=10, ge=1, le=1000)


def _paper_execution_enabled() -> bool:
    return os.getenv("KIASHA_PAPER_EXECUTION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _verified_company_and_price(code: str) -> tuple[dict, float, str]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is None:
        company = build_company_from_symbol(code)
        if company is None:
            raise HTTPException(status_code=404, detail="no verified BIAP data for symbol")
        raise HTTPException(status_code=409, detail="verified current price is unavailable for Paper execution")

    company = build_company_from_quote(quote, codal_symbol=quote.name)
    raw = getattr(quote, "last_price", None) or getattr(quote, "closing_price", None)
    if raw is None or float(raw) <= 0:
        raise HTTPException(status_code=409, detail="verified current price is unavailable for Paper execution")
    return company, float(raw), "verified-market-quote"


def _position_qty(account: dict, code: str) -> int:
    target = code.strip().upper()
    for position in account.get("positions", []):
        if str(position.get("code") or "").strip().upper() == target:
            return int(position.get("quantity") or 0)
    return 0


@router.post("/manual-paper/{code}")
def manual_paper_order(
    code: str,
    req: ManualPaperOrderRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user_id: str = Depends(require_user_id),
):
    """Execute the currently displayed deterministic Kiasha signal in Paper.

    This is user-initiated Paper simulation, not autonomous/live trading. The
    ordinary market-session check is intentionally disabled for this manual
    simulation so the user can test Paper outside TSE hours; a verified market
    reference price is still mandatory. Auto Invest keeps its market-hours guard.
    """
    if not _paper_execution_enabled():
        raise HTTPException(status_code=503, detail="Kiasha Paper execution is disabled")

    user_id = str(user_id)
    cached = AUDIT.get_idempotent_response(user_id=user_id, idempotency_key=idempotency_key)
    if cached is not None:
        return cached

    company, reference_price, reference_source = _verified_company_and_price(code)
    canonical_code = str(company.get("ticker") or code).strip().upper()
    recommendation = decide(company)
    requested_side = req.side.upper()

    proposal = {
        "source": "kiasha-deterministic-recommendation",
        "code": canonical_code,
        "action": recommendation.call,
        "score": float(recommendation.weighted_score),
        "executionAllowed": False,
    }

    if recommendation.call != requested_side:
        payload = {
            "allowed": False,
            "reasons": [f"Kiasha signal changed to {recommendation.call}; refresh the recommendation before trading"],
            "proposal": proposal,
            "paperExecution": False,
            "liveExecution": False,
            "manualPaper": True,
        }
        AUDIT.save_kiasha_ai_decision(
            user_id=user_id,
            code=canonical_code,
            horizon="manual",
            proposal=proposal,
            risk=None,
            result=payload,
            reference_price=reference_price,
            reference_source=reference_source,
            dry_run=False,
        )
        return payload

    account = AUDIT.ensure_paper_account(user_id=user_id, initial_cash=DEFAULT_PAPER_INITIAL_CASH)
    owned = _position_qty(account, canonical_code)
    if requested_side == "SELL" and req.quantity > owned:
        return {
            "allowed": False,
            "reasons": [f"SELL quantity {req.quantity} exceeds owned Paper position {owned}"],
            "proposal": proposal,
            "paperExecution": False,
            "liveExecution": False,
            "manualPaper": True,
        }

    # Manual Paper is testable outside exchange hours. All other deterministic
    # checks remain unchanged, and the fill stores enforce ownership/cash and
    # daily-notional invariants atomically.
    policy = replace(load_policy(), enforce_market_session=False)
    risk = evaluate_order_risk(
        side=requested_side,
        quantity=req.quantity,
        limit_price=reference_price,
        reference_price=reference_price,
        recommendation_score=float(recommendation.weighted_score),
        daily_notional_used=0.0,
        current_symbol_position=float(owned),
        policy=policy,
    )
    if not risk.allowed:
        payload = {
            "allowed": False,
            "reasons": list(risk.reasons),
            "proposal": proposal,
            "risk": risk.to_dict(),
            "paperExecution": False,
            "liveExecution": False,
            "manualPaper": True,
        }
        AUDIT.save_kiasha_ai_decision(
            user_id=user_id,
            code=canonical_code,
            horizon="manual",
            proposal=proposal,
            risk=risk.to_dict(),
            result=payload,
            reference_price=reference_price,
            reference_source=reference_source,
            dry_run=False,
        )
        return payload

    intent = build_order_intent(
        code=canonical_code,
        side=requested_side,
        quantity=req.quantity,
        limit_price=reference_price,
        mode="paper",
        recommendation_call=recommendation.call,
        recommendation_score=float(recommendation.weighted_score),
    )
    receipt = submit_order_intent(intent)
    kwargs = dict(
        user_id=user_id,
        code=canonical_code,
        horizon="manual",
        proposal=proposal,
        risk=risk.to_dict(),
        intent=intent,
        receipt=receipt,
        reference_price=reference_price,
        reference_source=reference_source,
        idempotency_key=idempotency_key,
    )
    try:
        result = SELL_STORE.commit_sell_fill(**kwargs) if requested_side == "SELL" else BUY_STORE.commit_buy_fill(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    result["manualPaper"] = True
    result["marketSessionGuardApplied"] = False
    result["liveExecution"] = False
    return result
