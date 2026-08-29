"""
Kiasha decision layer for BIAP.

Kiasha weights the BIAP analyst-agent team by observed track record. Until an
agent has enough genuinely evaluated observations, Kiasha uses a transparent,
non-historical experiment prior instead of invented performance history.
"""

from datetime import datetime, timezone
import math
from dataclasses import dataclass
from functools import lru_cache

from agents import run_team
from market_memory import save_analysis, save_symbol_snapshot
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from scenario_engine import build_scenarios

MATURITY_CAPS = {"experiment": 0.10, "observed": 0.20, "production": 0.35, "core": 0.50}
UNTRAINED_PRIOR_TRUST = 0.35
SCENARIO_MAX_BLEND_WEIGHT = 0.25


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


TRACK_RECORDS = {agent: AgentTrackRecord(agent, 0, 0.50, 1.00) for agent in ("fundamental", "risk", "forecast", "comparison", "technical", "flow")}


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
    prior = TRACK_RECORDS[agent]
    try:
        stats = _performance_store().agent_stats(agent)
    except (OSError, RuntimeError):
        stats = None
    if stats is None:
        return prior, "untrained-prior", 0
    if stats.evaluated_calls < MIN_OBSERVED_SAMPLES:
        return prior, "untrained-prior", stats.evaluated_calls
    observed = AgentTrackRecord(agent=agent, lifetime_calls=stats.evaluated_calls, accuracy=stats.directional_accuracy, pnl_std=stats.return_std)
    return observed, "observed", stats.evaluated_calls


@dataclass
class Decision:
    call: str
    weighted_score: float
    breakdown: list[dict]
    explanation: str
    scenario: dict | None = None


def _memory_symbol(company: dict) -> str:
    ticker = str(company.get("ticker") or "").strip()
    name = str(company.get("name_fa") or "").strip()
    return ticker if ticker and not ticker.isdigit() else name or ticker


def _record_observation(company: dict, decision: Decision) -> None:
    market = company.get("market") or {}
    raw_price = market.get("price")
    try:
        price = float(raw_price) if raw_price is not None else None
    except (TypeError, ValueError):
        price = None
    symbol = _memory_symbol(company)
    code = str(company.get("ticker") or symbol).strip()
    if not symbol:
        return
    generated_at = datetime.now(timezone.utc)
    try:
        _performance_store().record_recommendation(
            code=code, symbol=symbol, generated_at=generated_at.isoformat(), reference_price=price,
            kiasha_call=decision.call, weighted_score=decision.weighted_score, breakdown=decision.breakdown,
        )
    except Exception:
        pass

    availability = company.get("data_available") or {}
    has_verified_market = any(market.get(key) is not None for key in ("price", "change_percent", "pe", "market_cap"))
    if has_verified_market:
        if availability.get("tindex"):
            source = "kiasha:tindex"
        elif availability.get("market_memory"):
            source = str((company.get("market_memory") or {}).get("source") or "market_memory")
        else:
            source = "kiasha:tsetmc"
        try:
            save_symbol_snapshot(
                symbol=symbol,
                source=source,
                instrument_code=code or None,
                market=market.get("market_title"),
                observed_at=generated_at,
                payload={
                    "market": {
                        "price": market.get("price"), "last_price": market.get("last_price"),
                        "closing_price": market.get("closing_price"), "change_percent": market.get("change_percent"),
                        "pe": market.get("pe"), "market_cap": market.get("market_cap"),
                    },
                    "dataAvailability": availability,
                    "provenance": "verified inputs used by Kiasha decision",
                },
            )
        except Exception:
            pass

    try:
        save_analysis(
            scope="symbol", symbol=symbol, analysis_type="kiasha_decision", score=decision.weighted_score,
            created_at=generated_at,
            payload={
                "code": code, "symbol": symbol, "call": decision.call,
                "weightedScore": decision.weighted_score, "explanation": decision.explanation,
                "breakdown": decision.breakdown, "referencePrice": price,
                "dataAvailability": availability, "scenario": decision.scenario,
            },
        )
    except Exception:
        pass


def _scenario_signal(company: dict) -> tuple[dict | None, float | None, float]:
    """Return grounded scenario, base signal and conservative blend weight."""
    try:
        scenario = build_scenarios(company, persist=True)
    except Exception:
        return None, None, 0.0
    if scenario.get("status") != "ok":
        return scenario, None, 0.0
    base = ((scenario.get("scenarios") or {}).get("base") or {}).get("score")
    try:
        base_score = float(base)
        confidence = max(0.0, min(1.0, float(scenario.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return scenario, None, 0.0
    return scenario, max(-1.0, min(1.0, base_score)), min(SCENARIO_MAX_BLEND_WEIGHT, SCENARIO_MAX_BLEND_WEIGHT * confidence)


def decide(company: dict) -> Decision:
    votes = run_team(company)
    raw_weights = []
    breakdown = []
    for v in votes:
        tr, trust_source, observed_samples = _track_record_for_agent(v.agent)
        if trust_source == "observed":
            score, tier, n_factor = trust_score(tr)
        else:
            score, tier, n_factor = UNTRAINED_PRIOR_TRUST, "experiment", 0.0
        cap = MATURITY_CAPS[tier]
        weight = min(v.confidence * score, cap)
        raw_weights.append(weight)
        breakdown.append({
            "agent": v.agent, "vote": round(v.vote, 2), "confidence": v.confidence,
            "trust_score": round(score, 3), "trust_source": trust_source,
            "observed_samples": observed_samples, "maturity": tier,
            "weight_pre_norm": round(weight, 3), "reasoning": v.reasoning,
        })

    total_weight = sum(raw_weights) or 1e-9
    agent_score = sum(v.vote * w / total_weight for v, w in zip(votes, raw_weights))
    for entry, w in zip(breakdown, raw_weights):
        entry["weight_normalized"] = round(w / total_weight, 3)

    scenario, scenario_score, scenario_weight = _scenario_signal(company)
    weighted_score = agent_score
    if scenario_score is not None and scenario_weight > 0:
        weighted_score = agent_score * (1.0 - scenario_weight) + scenario_score * scenario_weight

    # Expose scenario details through the existing breakdown contract so old
    # clients remain compatible while newer mobile builds can render all three
    # grounded scenarios without requiring a breaking API response change.
    if scenario is not None:
        breakdown.append({
            "agent": "scenario",
            "vote": round(scenario_score or 0.0, 3),
            "confidence": float(scenario.get("confidence") or 0.0),
            "trust_score": None,
            "trust_source": "verified-scenario-engine",
            "observed_samples": int(scenario.get("historyObservations") or 0),
            "maturity": "grounded" if scenario.get("status") == "ok" else "insufficient",
            "weight_pre_norm": round(scenario_weight, 3),
            "weight_normalized": round(scenario_weight, 3),
            "reasoning": "سناریو بر پایه داده‌های معتبر موجود ساخته شده و قیمت آینده دقیق جعل نمی‌شود.",
            "scenario": scenario,
        })

    if weighted_score > 0.25:
        call = "BUY"
    elif weighted_score < -0.25:
        call = "SELL"
    else:
        call = "HOLD"

    agent_entries = [entry for entry in breakdown if entry.get("agent") != "scenario"]
    top = max(agent_entries, key=lambda e: e["weight_normalized"])
    scenario_note = ""
    if scenario is not None:
        if scenario_score is not None:
            scenario_note = f" Scenario base={scenario_score:+.2f}, confidence={scenario.get('confidence', 0):.0%}, blend={scenario_weight:.0%}."
        else:
            scenario_note = " Scenario evidence insufficient; no scenario weight applied."
    explanation = (
        f"Kiasha blend = {weighted_score:+.2f} -> {call}. "
        f"Heaviest voice: {top['agent']} (weight {top['weight_normalized']:.0%}, "
        f"maturity={top['maturity']}, trust={top['trust_source']}) - {top['reasoning']}." + scenario_note
    )
    decision = Decision(call, round(weighted_score, 3), breakdown, explanation, scenario)
    _record_observation(company, decision)
    return decision
