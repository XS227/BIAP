"""
Kiasha decision layer for BIAP.

Same core idea as the Kiasha capital allocator in the Arena project
(~ v7/capital_allocator.py on the TON VPS): don't trust every voice
equally — weight by a track record (trust_score = accuracy x stability
x n_factor), cap immature voices, and let evidence dominate over time.

There, Kiasha reallocated TON capital across trading strategies. Here,
Kiasha reallocates *decision weight* across the BIAP analyst-agent team
and turns the blend into a Buy/Hold/Sell call with an explanation.

Track records below are seeded/hardcoded placeholders standing in for
a real per-agent history (lifetime calls, rolling-window accuracy) that
a live BIAP backend would persist and update after each verified
outcome — mirroring how the arena's `kiasha_reallocations` /
`trust_score` fields are computed from real trade history.
"""

import math
from dataclasses import dataclass

from agents import AgentVote, run_team

MATURITY_CAPS = {
    "experiment": 0.10,  # <50 lifetime calls
    "observed": 0.20,    # 50-200 calls, or 200+ with weak accuracy
    "production": 0.35,  # 200+ calls, solid accuracy
    "core": 0.50,        # 1000+ calls, accuracy >= 0.55, stable
}


def maturity_tier(n_calls: int, accuracy: float) -> str:
    if n_calls >= 1000 and accuracy >= 0.55:
        return "core"
    if n_calls >= 200 and accuracy > 0.5:
        return "production"
    if n_calls >= 50 or (n_calls >= 200 and accuracy <= 0.5):
        return "observed"
    return "experiment"


@dataclass
class AgentTrackRecord:
    agent: str
    lifetime_calls: int
    accuracy: float        # fraction of past calls that were directionally correct
    pnl_std: float          # dispersion of past outcomes; lower = more stable


# Placeholder team history — replace with real per-agent stats once BIAP
# starts logging outcomes and can compute these like Arena does.
TRACK_RECORDS = {
    "fundamental": AgentTrackRecord("fundamental", 640, 0.58, 0.35),
    "risk":        AgentTrackRecord("risk",        310, 0.52, 0.55),
    "forecast":    AgentTrackRecord("forecast",     80, 0.49, 0.90),
    "comparison":  AgentTrackRecord("comparison",  1240, 0.56, 0.40),
}


def trust_score(tr: AgentTrackRecord) -> tuple[float, str, float]:
    stability = 1 / (1 + tr.pnl_std)
    n_factor = math.log1p(tr.lifetime_calls) / math.log1p(200)
    n_factor = min(n_factor, 1.5)  # let core agents exceed the 200-call reference a bit
    score = tr.accuracy * stability * n_factor
    tier = maturity_tier(tr.lifetime_calls, tr.accuracy)
    return score, tier, n_factor


@dataclass
class Decision:
    call: str            # BUY / HOLD / SELL
    weighted_score: float
    breakdown: list[dict]
    explanation: str


def decide(company: dict) -> Decision:
    votes = run_team(company)

    raw_weights = []
    breakdown = []
    for v in votes:
        tr = TRACK_RECORDS[v.agent]
        score, tier, n_factor = trust_score(tr)
        cap = MATURITY_CAPS[tier]
        weight = min(v.confidence * score, cap)
        raw_weights.append(weight)
        breakdown.append({
            "agent": v.agent,
            "vote": round(v.vote, 2),
            "confidence": v.confidence,
            "trust_score": round(score, 3),
            "maturity": tier,
            "weight_pre_norm": round(weight, 3),
            "reasoning": v.reasoning,
        })

    total_weight = sum(raw_weights) or 1e-9
    weighted_score = sum(
        v.vote * w / total_weight for v, w in zip(votes, raw_weights)
    )
    for entry, w in zip(breakdown, raw_weights):
        entry["weight_normalized"] = round(w / total_weight, 3)

    if weighted_score > 0.25:
        call = "BUY"
    elif weighted_score < -0.25:
        call = "SELL"
    else:
        call = "HOLD"

    top = max(breakdown, key=lambda e: e["weight_normalized"])
    explanation = (
        f"Kiasha blend = {weighted_score:+.2f} -> {call}. "
        f"Heaviest voice: {top['agent']} "
        f"(weight {top['weight_normalized']:.0%}, maturity={top['maturity']}) - "
        f"{top['reasoning']}"
    )

    return Decision(call, round(weighted_score, 3), breakdown, explanation)
