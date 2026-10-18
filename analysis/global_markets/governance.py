"""BIAP adapter for the canonical DMA Decision Agent 8.

Thresholds are kept aligned with XS227/dma-agent/decision_pipeline.py:
accept >= 0.55, escalate to human review from 0.35 to <0.55, and abstain
below 0.35. BIAP's Evidence BLOCK is the application equivalent of an
out-of-scope/failed capability gate. Agent 9 may add a hard block only to a
NEW positive call; it never creates a directional decision.
"""
from __future__ import annotations

from typing import Optional

from .models import DistressAssessment, EvidenceAssessment, GovernanceAssessment


MIN_BUY_PEER_GROUP = 8
BUY_DISTRESS_OK = frozenset({"LOW_RISK", "NOT_APPLICABLE"})


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
    critical_data_gaps: tuple[str, ...] = (),
    buy_review_rules: bool = False,
    peer_group_size: Optional[int] = None,
    positive_signal_agents: tuple[str, ...] = (),
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

    # Fail closed: a positive call needs the critical comparison evidence that
    # a derived, time-limited input (e.g. the daily peer scan) can silently
    # remove. Without it the call is routed to REVIEW instead of being accepted,
    # so cache expiry alone can never turn NO_RECOMMENDATION into a BUY.
    # Conservative BUY rules (all markets). Each is a reason to ask a human,
    # never to invent a negative call: the BUY becomes REVIEW / NO_RECOMMENDATION.
    #  1. distress assessment must be LOW_RISK (NOT_APPLICABLE is allowed: banks
    #     and insurers have no operating-distress model; INSUFFICIENT_DATA is not);
    #  2. the sector peer group behind the valuation comparison needs >= 8 valid
    #     companies (unknown size counts as not verifiable);
    #  3. a relative-P/E (comparison) signal alone cannot carry a BUY.
    rule_reasons: list[str] = []
    if proposed_call == "BUY_CANDIDATE" and buy_review_rules:
        if distress.status not in BUY_DISTRESS_OK:
            rule_reasons.append(f"distress assessment is {distress.status}, a BUY requires LOW_RISK")
        if peer_group_size is None or peer_group_size < MIN_BUY_PEER_GROUP:
            shown = "unverified" if peer_group_size is None else str(peer_group_size)
            rule_reasons.append(
                f"sector peer group {shown} (< {MIN_BUY_PEER_GROUP} valid companies); relative valuation is not reliable"
            )
        others = [a for a in positive_signal_agents if a != "comparison"]
        if not others:
            rule_reasons.append("the only positive signal is relative P/E (comparison); no independent supporting signal")

    if proposed_call == "BUY_CANDIDATE" and (critical_data_gaps or rule_reasons):
        reviews.extend(critical_data_gaps)
        reviews.extend(rule_reasons)
        return GovernanceAssessment(
            action="REVIEW",
            final_call="NO_RECOMMENDATION",
            accepted=False,
            escalated=True,
            abstained=True,
            hard_blocks=(),
            review_reasons=tuple(reviews),
            reasoning="Escalated to human review (fail-closed): " + "; ".join(reviews),
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
