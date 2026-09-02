"""Deterministic bridge from Kiasha AI proposals to PaperBroker.

Claude remains proposal-only. BUY and SELL proposals can become PAPER intents
only after deterministic checks. SELL is ownership-bounded and can never create
a short position. There is no live/AUTO execution path here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Any, Optional

from execution import ExecutionMode, ExecutionPolicyError, build_order_intent, submit_order_intent
from kiasha_ai import KiashaAIProposal
from risk import RiskDecision, RiskPolicy, evaluate_order_risk

# Registers authenticated, server-backed bookkeeping endpoints on the existing
# manual Paper router. This remains bookkeeping-only and never enables live
# broker execution.
import manual_trade_routes  # noqa: F401,E402


@dataclass(frozen=True)
class PaperGateResult:
    allowed: bool
    reasons: list[str]
    proposal: dict[str, Any]
    risk: Optional[dict[str, Any]]
    intent: Optional[dict[str, Any]]
    receipt: Optional[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "proposal": self.proposal,
            "risk": self.risk,
            "intent": self.intent,
            "receipt": self.receipt,
            "paperExecution": self.receipt is not None,
            "liveExecution": False,
        }


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _signed_score(proposal: KiashaAIProposal) -> float:
    if proposal.action == "BUY":
        return proposal.confidence
    if proposal.action == "SELL":
        return -proposal.confidence
    return 0.0


def evaluate_ai_paper_proposal(
    proposal: KiashaAIProposal,
    *,
    portfolio_value: float,
    reference_price: Optional[float],
    daily_notional_used: float = 0.0,
    current_symbol_position: float = 0.0,
    quote_fetched_at: Optional[float] = None,
    risk_policy: Optional[RiskPolicy] = None,
    min_confidence: Optional[float] = None,
    max_position_pct: Optional[float] = None,
    execute: bool = False,
) -> PaperGateResult:
    proposal_dict = proposal.to_dict()
    reasons: list[str] = []
    threshold = min_confidence if min_confidence is not None else _env_float("KIASHA_PAPER_MIN_CONFIDENCE", 0.55)
    threshold = max(0.0, min(1.0, threshold))

    if proposal.execution_allowed:
        reasons.append("AI proposal must remain executionAllowed=false")
    if proposal.action not in {"BUY", "SELL"}:
        reasons.append("Paper gate accepts BUY or SELL proposals only")
    if proposal.confidence < threshold:
        reasons.append(f"AI confidence {proposal.confidence:.3f} below Paper minimum {threshold:.3f}")
    if portfolio_value <= 0:
        reasons.append("portfolio value must be positive")
    if reference_price is None or reference_price <= 0:
        reasons.append("verified positive reference price is required")
    if proposal.position_pct <= 0:
        reasons.append("proposal positionPct must be positive")
    if max_position_pct is not None and max_position_pct <= 0:
        reasons.append("max_position_pct must be positive")
    if proposal.action == "SELL" and current_symbol_position <= 0:
        reasons.append("cannot SELL a Paper position that this account does not own")
    if reasons:
        return PaperGateResult(False, reasons, proposal_dict, None, None, None)

    assert reference_price is not None
    effective_pct = float(proposal.position_pct)
    if max_position_pct is not None:
        effective_pct = min(effective_pct, float(max_position_pct))
    target_notional = portfolio_value * effective_pct / 100.0
    quantity = math.floor(target_notional / reference_price)
    if proposal.action == "SELL":
        quantity = min(quantity, int(current_symbol_position))
    if quantity <= 0:
        action = proposal.action.lower()
        return PaperGateResult(False, [f"proposal size is too small to {action} one share at the verified reference price"], proposal_dict, None, None, None)

    side = proposal.action
    score = _signed_score(proposal)
    risk: RiskDecision = evaluate_order_risk(
        side=side,
        quantity=quantity,
        limit_price=reference_price,
        reference_price=reference_price,
        recommendation_score=score,
        daily_notional_used=daily_notional_used,
        current_symbol_position=current_symbol_position,
        quote_fetched_at=quote_fetched_at,
        policy=risk_policy,
    )
    if not risk.allowed:
        return PaperGateResult(False, list(risk.reasons), proposal_dict, risk.to_dict(), None, None)

    if side == "SELL" and quantity > int(current_symbol_position):
        return PaperGateResult(False, ["SELL quantity exceeds owned Paper position"], proposal_dict, risk.to_dict(), None, None)

    try:
        intent = build_order_intent(
            code=proposal.code,
            side=side,
            quantity=quantity,
            limit_price=reference_price,
            mode=ExecutionMode.PAPER.value,
            recommendation_call=proposal.action,
            recommendation_score=score,
        )
    except ExecutionPolicyError as exc:
        return PaperGateResult(False, [str(exc)], proposal_dict, risk.to_dict(), None, None)

    receipt = submit_order_intent(intent) if execute else None
    return PaperGateResult(True, [], proposal_dict, risk.to_dict(), intent, receipt)
