"""Guarded execution layer for BIAP.

This module intentionally separates analysis from order execution.
It supports PAPER and APPROVAL flows only. AUTO/LIVE execution is explicitly
blocked until a real broker adapter, credentials, compliance review, and risk
controls are implemented and enabled deliberately.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

from broker import PaperBroker


class ExecutionMode(str, Enum):
    PAPER = "paper"
    APPROVAL = "approval"
    AUTO = "auto"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class OrderIntent:
    id: str
    code: str
    side: str
    quantity: int
    limit_price: Optional[float]
    mode: str
    status: str
    recommendation_call: str
    recommendation_score: float
    created_at: str
    note: str


class ExecutionPolicyError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_intent(*, code: str, side: str, quantity: int, mode: str,
                    recommendation_call: str, recommendation_score: float) -> None:
    if not code.strip():
        raise ExecutionPolicyError("stock code is required")
    if side not in {OrderSide.BUY.value, OrderSide.SELL.value}:
        raise ExecutionPolicyError("side must be BUY or SELL")
    if quantity <= 0:
        raise ExecutionPolicyError("quantity must be greater than zero")
    if mode not in {m.value for m in ExecutionMode}:
        raise ExecutionPolicyError("unsupported execution mode")
    if mode == ExecutionMode.AUTO.value:
        raise ExecutionPolicyError("AUTO execution is disabled")

    # Analysis and execution stay independent, but obvious contradictions are
    # rejected at the policy boundary.
    if side == OrderSide.BUY.value and recommendation_call == "SELL":
        raise ExecutionPolicyError("BUY conflicts with current SELL recommendation")
    if side == OrderSide.SELL.value and recommendation_call == "BUY":
        raise ExecutionPolicyError("SELL conflicts with current BUY recommendation")

    if not -1.0 <= recommendation_score <= 1.0:
        raise ExecutionPolicyError("recommendation score must be between -1 and 1")


def build_order_intent(*, code: str, side: str, quantity: int,
                       limit_price: Optional[float], mode: str,
                       recommendation_call: str,
                       recommendation_score: float) -> dict:
    validate_intent(
        code=code,
        side=side,
        quantity=quantity,
        mode=mode,
        recommendation_call=recommendation_call,
        recommendation_score=recommendation_score,
    )

    if limit_price is not None and limit_price <= 0:
        raise ExecutionPolicyError("limit_price must be positive when provided")

    status = "SIMULATED" if mode == ExecutionMode.PAPER.value else "PENDING_APPROVAL"
    note = (
        "Paper-only simulation; no broker request was sent."
        if mode == ExecutionMode.PAPER.value
        else "Approval required; no broker request was sent."
    )

    intent = OrderIntent(
        id=str(uuid.uuid4()),
        code=code.upper(),
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        mode=mode,
        status=status,
        recommendation_call=recommendation_call,
        recommendation_score=round(recommendation_score, 4),
        created_at=_now_iso(),
        note=note,
    )
    return asdict(intent)


_PAPER_BROKER = PaperBroker()


def submit_order_intent(intent: dict) -> dict:
    """Submit an already-built intent.

    PAPER is handed to a Broker (see broker.py) to produce a fill receipt.
    APPROVAL remains pending and never reaches a broker at all -- it waits on
    a human, by design. AUTO is never accepted. No real broker is connected.
    """
    mode = intent.get("mode")
    if mode == ExecutionMode.AUTO.value:
        raise ExecutionPolicyError("AUTO execution is disabled")
    if mode == ExecutionMode.APPROVAL.value:
        return {
            **intent,
            "status": "PENDING_APPROVAL",
            "submittedAt": _now_iso(),
            "broker": None,
            "brokerOrderId": None,
        }
    if mode == ExecutionMode.PAPER.value:
        return _PAPER_BROKER.submit(intent)
    raise ExecutionPolicyError("unsupported execution mode")


def approve_order_intent(intent: dict) -> dict:
    """Transition a PENDING_APPROVAL intent to APPROVED.

    Idempotent by state, matching submit_order_intent's own idempotency
    design: re-approving an already-APPROVED (or otherwise resolved) intent
    returns it unchanged rather than re-timestamping or erroring.
    """
    if intent.get("mode") != ExecutionMode.APPROVAL.value:
        raise ExecutionPolicyError("only an approval-mode intent can be approved")
    if intent.get("status") != "PENDING_APPROVAL":
        return intent
    return {**intent, "status": "APPROVED", "resolvedAt": _now_iso()}


def reject_order_intent(intent: dict, *, reason: Optional[str] = None) -> dict:
    """Transition a PENDING_APPROVAL intent to REJECTED. Idempotent by state."""
    if intent.get("mode") != ExecutionMode.APPROVAL.value:
        raise ExecutionPolicyError("only an approval-mode intent can be rejected")
    if intent.get("status") != "PENDING_APPROVAL":
        return intent
    return {**intent, "status": "REJECTED", "resolvedAt": _now_iso(), "rejectionReason": reason}
