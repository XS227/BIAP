"""Agent 8 — Decision Governance for BIAP Global.

This agent is deliberately downstream from scoring/evidence/distress. It does
not invent a BUY/SELL thesis. It controls whether the draft decision may be
accepted, should be escalated for review, or must abstain.
"""
from __future__ import annotations

from .models import DistressAssessment, EvidenceAssessment, GovernanceAssessment


def decision_governance_agent(
    *,
    proposed_call: str,
    score: float,
    overall_confidence: float,
    decision_confidence: float,
    evidence: EvidenceAssessment,
    distress: DistressAssessment,
) -> GovernanceAssessment:
    hard_blocks: list[str] = []
    reviews: list[str] = []

    if evidence.status == "BLOCK":
        hard_blocks.append("evidence gate blocked the decision")
    if overall_confidence < 0.35:
        hard_blocks.append(f"overall calibrated confidence {overall_confidence:.2f} < 0.35")
    if proposed_call == "BUY_CANDIDATE" and evidence.status != "PASS":
        hard_blocks.append(f"new positive call requires PASS evidence, got {evidence.status}")
    if proposed_call == "BUY_CANDIDATE" and distress.positive_block:
        hard_blocks.append(f"distress safety gate: {distress.reasoning}")

    if evidence.status == "WARN":
        reviews.append("evidence requires review")
    if evidence.contradictions:
        reviews.append("high-confidence agent disagreement")
    if distress.status == "ELEVATED_RISK":
        reviews.append("elevated independent distress risk")
    if decision_confidence < 0.45:
        reviews.append(f"decision confidence {decision_confidence:.2f} < 0.45")

    if hard_blocks:
        return GovernanceAssessment(
            action="ABSTAIN",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=False,
            abstained=True,
            hard_blocks=tuple(hard_blocks),
            review_reasons=tuple(reviews),
            reasoning="; ".join(hard_blocks + reviews),
        )

    # Negative calls may be accepted when the evidence is strong enough even if
    # the distress sidecar corroborates them. Distress does not lower evidence
    # confidence merely because the company is weak.
    if proposed_call == "AVOID_OR_REVIEW":
        if reviews:
            return GovernanceAssessment(
                action="REVIEW",
                final_call="AVOID_OR_REVIEW",
                accepted=False,
                escalated=True,
                abstained=False,
                hard_blocks=(),
                review_reasons=tuple(reviews),
                reasoning="negative/caution call retained but requires review: " + "; ".join(reviews),
            )
        return GovernanceAssessment(
            action="ACCEPT",
            final_call="AVOID_OR_REVIEW",
            accepted=True,
            escalated=False,
            abstained=False,
            reasoning="negative/caution draft accepted after evidence and distress governance checks",
        )

    if proposed_call == "BUY_CANDIDATE":
        if reviews:
            return GovernanceAssessment(
                action="REVIEW",
                final_call="HOLD_OR_WATCH",
                accepted=False,
                escalated=True,
                abstained=False,
                review_reasons=tuple(reviews),
                reasoning="positive draft withheld pending review: " + "; ".join(reviews),
            )
        return GovernanceAssessment(
            action="ACCEPT",
            final_call="BUY_CANDIDATE",
            accepted=True,
            escalated=False,
            abstained=False,
            reasoning="positive draft accepted after PASS evidence and distress safety checks",
        )

    if reviews:
        return GovernanceAssessment(
            action="REVIEW",
            final_call="HOLD_OR_WATCH",
            accepted=False,
            escalated=True,
            abstained=False,
            review_reasons=tuple(reviews),
            reasoning="watch/hold draft requires review: " + "; ".join(reviews),
        )

    return GovernanceAssessment(
        action="ACCEPT",
        final_call="HOLD_OR_WATCH",
        accepted=True,
        escalated=False,
        abstained=False,
        reasoning=f"neutral/watch draft accepted (score={score:.3f}, confidence={overall_confidence:.3f})",
    )
