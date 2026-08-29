"""
Kiasha decision layer for BIAP.

Kiasha weights the BIAP analyst-agent team by observed track record. Seeded
records are explicitly-labelled fallbacks only; real evaluated performance takes
over once the conservative sample threshold is reached.
"""

from datetime import datetime, timezone
import math
from dataclasses import dataclass
from functools import lru_cache

from agents import run_team
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore

MATURITY_CAPS = {
    "experiment": 0.10,
    "observed": 0.20,
    "production": 0.35,
    "core": 0.50,
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
    accuracy: float
    pnl_std: float


# Fallback history only. New evidence dimensions start conservatively in the
# experiment tier until enough genuine observations exist.
TRACK_RECORDS = {
    "fundamental": AgentTrackRecord("fundamental", 640, 0.58, 0.35),
    "risk": AgentTrackRecord("risk", 310, 0.52, 0.55),
    "forecast": AgentTrackRecord("forecast", 80, 0.49, 0.90),
    "comparison": AgentTrackRecord("comparison", 1240, 0.56, 0.40),
    "technical": AgentTrackRecord("technical", 0, 0.50, 1.00),
    "flow": AgentTrackRecord("flow", 0, 0.50, 1.00),
}


def trust_score(tr: AgentTrackRecord) -> tuple[float, str, float]:
    stability = 1 / (1 + tr.pnl_std)
    n_factor = math.log1p(tr.lifetime_calls) / math.log1p(200)
    n_factor = min(n_factor, 1.5)
    score = tr.accuracy * stability * n_factor
    tier = maturity_tier(tr.lifetime_calls, tr.accuracy)
    return score, tier, n_factor


@lru_cache(maxsize=1)
def _performance_store() -> PerformanceStore:
    return PerformanceStore()


def _track_record_for_agent(agent: str) -> tuple[AgentTrackRecord, str, int]:
    fallback = TRACK_RECORDS[agent]
    try:
        stats = _performance_store().agent_stats(agent)
    except (OSError, RuntimeError):
        stats = None
    if stats is None:
        return fallback, "fallback", 0
    if stats.evaluated_calls < MIN_OBSERVED_SAMPLES:
        return fallback, "fallback", stats.evaluated_calls
    observed = AgentTrackRecord(
        agent=agent,
        lifetime_calls=stats.evaluated_calls,
        accuracy=stats.directional_accuracy,
        pnl_std=stats.return_std,
    )
    return observed, "observed", stats.evaluated_calls


@dataclass
class Decision:
    call: str
    weighted_score: float
    breakdown: list[dict]
    explanation: str


def _record_observation(company: dict, decision: Decision) -> None:
    market = company.get("market") or {}
    raw_price = market.get("price")
    try:
        price = float(raw_price) if raw_price is not None else None
    except (TypeError, ValueError):
        price = None
    symbol = str(company.get("name_fa") or company.get("ticker") or "").strip()
    code = str(company.get("ticker") or symbol).strip()
    if not symbol:
        return
    try:
        _performance_store().record_recommendation(
            code=code,
            symbol=symbol,
            generated_at=datetime.now(timezone.utc).isoformat(),
            reference_price=price,
            kiasha_call=decision.call,
            weighted_score=decision.weighted_score,
            breakdown=decision.breakdown,
        )
    except Exception:
        return


def decide(company: dict) -> Decision:
    votes = run_team(company)

    raw_weights = []
    breakdown = []
    for v in votes:
        tr, trust_source, observed_samples = _track_record_for_agent(v.agent)
        score, tier, n_factor = trust_score(tr)
        cap = MATURITY_CAPS[tier]
        weight = min(v.confidence * score, cap)
        raw_weights.append(weight)
        breakdown.append({
            "agent": v.agent,
            "vote": round(v.vote, 2),
            "confidence": v.confidence,
            "trust_score": round(score, 3),
            "trust_source": trust_source,
            "observed_samples": observed_samples,
            "maturity": tier,
            "weight_pre_norm": round(weight, 3),
            "reasoning": v.reasoning,
        })

    total_weight = sum(raw_weights) or 1e-9
    weighted_score = sum(v.vote * w / total_weight for v, w in zip(votes, raw_weights))
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
        f"(weight {top['weight_normalized']:.0%}, maturity={top['maturity']}, "
        f"trust={top['trust_source']}) - {top['reasoning']}"
    )

    decision = Decision(call, round(weighted_score, 3), breakdown, explanation)
    _record_observation(company, decision)
    return decision
