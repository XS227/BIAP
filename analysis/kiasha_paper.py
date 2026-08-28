"""Deterministic bridge from Kiasha AI proposals to PaperBroker.

Claude remains proposal-only. This module is the policy boundary that may turn a
validated BUY proposal into a PAPER order intent after deterministic checks.
It never enables AUTO/live execution and never talks to a real broker.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Any, Optional

from execution import ExecutionMode, ExecutionPolicyError, build_order_intent, submit_order_intent
from kiasha_ai import KiashaAIProposal
from risk import RiskDecision, RiskPolicy, evaluate_order_risk


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
    risk_policy: Optional[RiskPolicy] = None,
    min_confidence: Optional[float] = None,
    execute: bool = False,
) -> PaperGateResult:
    """Evaluate, and optionally execute, a Kiasha proposal in PAPER mode only.

    ``execute=False`` is a dry run. ``execute=True`` may call PaperBroker only
    after every deterministic check passes. There is no code path to AUTO/live.
    """
    proposal_dict = proposal.to_dict()
    reasons: list[str] = []

    threshold = min_confidence
    if threshold is None:
        threshold = _env_float("KIASHA_PAPER_MIN_CONFIDENCE", 0.55)
    threshold = max(0.0, min(1.0, threshold))

    if proposal.execution_allowed:
        reasons.append("AI proposal must remain executionAllowed=false")
    if proposal.action != "BUY":
        reasons.append("Paper entry gate currently accepts BUY proposals only")
    if proposal.confidence < threshold:
        reasons.append(
            f"AI confidence {proposal.confidence:.3f} below Paper minimum {threshold:.3f}"
        )
    if portfolio_value <= 0:
        reasons.append("portfolio value must be positive")
    if reference_price is None or reference_price <= 0:
        reasons.append("verified positive reference price is required")
    if proposal.position_pct <= 0:
        reasons.append("proposal positionPct must be positive")

    if reasons:
        return PaperGateResult(False, reasons, proposal_dict, None, None, None)

    assert reference_price is not None
    target_notional = portfolio_value * proposal.position_pct / 100.0
    quantity = math.floor(target_notional / reference_price)
    if quantity <= 0:
        return PaperGateResult(
            False,
            ["proposal size is too small to buy one share at the verified reference price"],
            proposal_dict,
            None,
            None,
            None,
        )

    score = _signed_score(proposal)
    risk: RiskDecision = evaluate_order_risk(
        side="BUY",
        quantity=quantity,
        limit_price=reference_price,
        reference_price=reference_price,
        recommendation_score=score,
        daily_notional_used=daily_notional_used,
        current_symbol_position=current_symbol_position,
        policy=risk_policy,
    )
    if not risk.allowed:
        return PaperGateResult(False, list(risk.reasons), proposal_dict, risk.to_dict(), None, None)

    try:
        intent = build_order_intent(
            code=proposal.code,
            side="BUY",
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
