"""BIAP adapter for the canonical DMA Decision Agent 8.

Thresholds are kept aligned with XS227/dma-agent/decision_pipeline.py:
accept >= 0.55, escalate to human review from 0.35 to <0.55, and abstain
below 0.35. BIAP's Evidence BLOCK is the application equivalent of an
out-of-scope/failed capability gate. Agent 9 may add a hard block only to a
NEW positive call; it never creates a directional decision.
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
    accept_threshold: float = 0.55,
    escalate_threshold: float = 0.35,
) -> GovernanceAssessment:
    hard_blocks: list[str] = []
    reviews: list[str] = []

    if evidence.status == "BLOCK":
        hard_blocks.append("task/evidence gate is out of scope or blocked")

    if proposed_call == "BUY_CANDIDATE" and distress.positive_block:
        hard_blocks.append(f"Agent 9 distress safety gate: {distress.reasoning}")

    if hard_blocks:
        return GovernanceAssessment(
            action="ABSTAIN",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=False,
            abstained=True,
            hard_blocks=tuple(hard_blocks),
            review_reasons=(),
            reasoning="Abstained: " + "; ".join(hard_blocks),
        )

    conf = max(0.0, min(1.0, float(overall_confidence)))

    # WARN evidence is research-grade only. It must never be promoted to an
    # actionable call merely because the model confidence is numerically high.
    # This is especially important for Germany's long-tail listings where a
    # public-vendor fundamentals snapshot may be available before an official
    # annual report has been resolved by the ingestion layer.
    if evidence.status == "WARN":
        reviews.append("evidence gate returned WARN")
        if evidence.contradictions:
            reviews.append("high-confidence agent disagreement")
        if distress.status == "ELEVATED_RISK":
            reviews.append("elevated independent distress risk")
        return GovernanceAssessment(
            action="REVIEW",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=True,
            abstained=True,
            hard_blocks=(),
            review_reasons=tuple(reviews),
            reasoning="Escalated to human review: " + "; ".join(reviews),
        )

    # A disagreement between otherwise well-supported analysis agents is not an
    # evidence-quality defect, but it must still prevent automatic acceptance.
    # Keep Evidence PASS truthful while routing the decision itself to REVIEW.
    if evidence.contradictions:
        reviews.append("high-confidence agent disagreement")
        if distress.status == "ELEVATED_RISK":
            reviews.append("elevated independent distress risk")
        return GovernanceAssessment(
            action="REVIEW",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=True,
            abstained=True,
            hard_blocks=(),
            review_reasons=tuple(reviews),
            reasoning="Escalated to human review: " + "; ".join(reviews),
        )

    if conf >= accept_threshold:
        return GovernanceAssessment(
            action="ACCEPT",
            final_call=proposed_call,
            accepted=True,
            escalated=False,
            abstained=False,
            reasoning=f"Accepted draft decision at calibrated confidence {conf:.2f}.",
        )

    if conf >= escalate_threshold:
        reviews.append(
            f"calibrated confidence {conf:.2f} below accept threshold {accept_threshold:.2f}"
        )
        if evidence.status == "WARN":
            reviews.append("evidence gate returned WARN")
        if evidence.contradictions:
            reviews.append("high-confidence agent disagreement")
        if distress.status == "ELEVATED_RISK":
            reviews.append("elevated independent distress risk")
        return GovernanceAssessment(
            action="REVIEW",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=True,
            abstained=True,
            hard_blocks=(),
            review_reasons=tuple(reviews),
            reasoning="Escalated to human review: " + "; ".join(reviews),
        )

    return GovernanceAssessment(
        action="ABSTAIN",
        final_call="NO_RECOMMENDATION",
        accepted=False,
        escalated=False,
        abstained=True,
        hard_blocks=(),
        review_reasons=(
            f"calibrated confidence {conf:.2f} below escalation threshold {escalate_threshold:.2f}",
        ),
        reasoning=f"Abstained: calibrated confidence {conf:.2f} too low to act on.",
    )
