"""Decision-logic version switch and engine labelling.

``DECISION_LOGIC_VERSION`` selects the conservative-engine decision logic:

* ``v1`` (default, and the fallback for any unknown value): the logic that was live on 2026-10-30. It is what the
  frozen paper portfolio (``research/paper_portfolio_2026-10-20.json``) and the paper's Chapter 4 measure and it must not
  change. The investment mode (``investment_mode.py``) is **never** switched by this setting.
* ``v2``: fixes P1.10 (abstaining agents carry no weight), P1.3 (Agent 8 disagreement rule), graded price freshness and
  related items from ``docs/BIAP_FIX_PLAN.md``. Opt-in; every difference is listed in
  ``docs/CHANGELOG_DECISION_LOGIC.md``.

Engines (P1.11): ``conservative`` = absolute thresholds + Agent 8 governance (the stored ``call``); ``investment`` =
rank-based tiers of the investment mode. ``engines_block`` gives every API payload an explicit, labelled description of
both so no client has to guess which score or label belongs to which engine.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional

V1 = "v1"
V2 = "v2"
VALID_VERSIONS = (V1, V2)

ENGINE_CONSERVATIVE = "conservative"
ENGINE_INVESTMENT = "investment"

ENGINE_LABEL = {
    ENGINE_CONSERVATIVE: "Conservative check",
    ENGINE_INVESTMENT: "Investment ranking",
}
ENGINE_DESCRIPTION = {
    ENGINE_CONSERVATIVE: "Absolute thresholds and Agent 8 governance; a stock can be left without a recommendation.",
    ENGINE_INVESTMENT: "Relative ranking within this exchange (BUY / ACCUMULATE / HOLD / REDUCE / SELL).",
}


def logic_version(value: Optional[str] = None) -> str:
    """Configured decision-logic version; anything but ``v2`` means ``v1`` (the frozen, paper-measured logic)."""
    raw = os.environ.get("DECISION_LOGIC_VERSION") if value is None else value
    text = str(raw or "").strip().lower()
    return V2 if text == V2 else V1


def is_v2(value: Optional[str] = None) -> bool:
    return logic_version(value) == V2


def _round(value: Any, digits: int = 6) -> Optional[float]:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def engines_block(result: Mapping[str, Any], investment: Optional[Mapping[str, Any]]) -> dict:
    """Both engines side by side for one analysed stock (additive API field ``engines``).

    ``displayed`` names the engine whose label a client shows as the decision: the investment tier when one exists,
    otherwise the conservative call. The numbers are never mixed: ``conservative.score`` is the fresh analysis score,
    ``investment.score`` is the ranking score of the stored ledger row.
    """
    conservative = {
        "engine": ENGINE_CONSERVATIVE,
        "label": ENGINE_LABEL[ENGINE_CONSERVATIVE],
        "description": ENGINE_DESCRIPTION[ENGINE_CONSERVATIVE],
        "call": result.get("call"),
        "score": _round(result.get("score")),
        "confidence": _round(result.get("confidence")),
        "logicVersion": logic_version(),
    }
    block: dict = {"conservative": conservative, "displayed": ENGINE_CONSERVATIVE, "investment": None}
    if investment:
        block["investment"] = {
            "engine": ENGINE_INVESTMENT,
            "label": ENGINE_LABEL[ENGINE_INVESTMENT],
            "description": ENGINE_DESCRIPTION[ENGINE_INVESTMENT],
            "tier": investment.get("tier"),
            "score": _round(investment.get("score")),
            "confidence": _round(investment.get("confidence")),
            "rank": investment.get("rank"),
            "percentile": _round(investment.get("percentile")),
        }
        block["displayed"] = ENGINE_INVESTMENT
    return block


# --- P1.10 (v2): abstaining agents carry no weight -----------------------------------------------------------------------
# Same rule as the investment mode (``InvestmentConfig.data_min_confidence`` / ``min_agents_full_confidence``): an agent
# whose confidence is below 0.30 has no usable data (the core agents emit 0.0 = unavailable and 0.25 = abstaining), so it
# is left out of both the score and the confidence mean; confidence is scaled down only when fewer than 4 agents remain.
DATA_MIN_CONFIDENCE = 0.30
MIN_AGENTS_FULL_CONFIDENCE = 4


def active_signals(signals) -> list:
    return [s for s in signals if float(s.confidence) >= DATA_MIN_CONFIDENCE]


def weighted_score_v2(signals) -> tuple[float, float]:
    """(score, decision confidence) over the active agents only; weights are the active agents' confidence shares."""
    active = active_signals(signals)
    weighted = 0.0
    total = 0.0
    for signal in active:
        confidence = max(0.0, min(1.0, float(signal.confidence)))
        weighted += max(-1.0, min(1.0, float(signal.vote))) * confidence
        total += confidence
    if total <= 0:
        return 0.0, 0.0
    mean_confidence = total / len(active)
    if len(active) < MIN_AGENTS_FULL_CONFIDENCE:
        mean_confidence *= len(active) / MIN_AGENTS_FULL_CONFIDENCE
    return weighted / total, mean_confidence


# --- P1.3 (v2): Agent 8 disagreement only between agents measuring the same dimension -------------------------------------
# v1 treats any confident positive agent (vote >= +0.35, confidence >= 0.55) against any confident negative agent
# (vote <= -0.35) as a contradiction, so "high-quality company" (quality) against "volatile share price" (risk) sends a
# decision to REVIEW (SAP, 2026-10-30). Those agents measure different things. v2 keeps the same numeric limits but
# compares agents only inside one dimension:
#   business   fundamental, quality   (what the company earns and owes)
#   market     forecast, liquidity    (what the share price and trading do)
#   risk       risk                   (alone: nothing to contradict)
#   valuation  comparison             (alone)
AGENT_DIMENSION = {
    "fundamental": "business", "quality": "business",
    "forecast": "market", "liquidity": "market",
    "risk": "risk",
    "comparison": "valuation",
}
DISAGREE_CONFIDENCE = 0.55
DISAGREE_POSITIVE = 0.35
DISAGREE_NEGATIVE = -0.35


def _items(signals):
    """(agent, vote, confidence) triples from AgentSignal objects or from an ``agent -> (vote, confidence)`` mapping."""
    if hasattr(signals, "items"):
        return [(agent, float(v), float(c)) for agent, (v, c) in signals.items()]
    return [(s.agent, float(s.vote), float(s.confidence)) for s in signals]


def _confident_sides(items):
    pos, neg = [], []
    for agent, vote, confidence in items:
        if confidence < DISAGREE_CONFIDENCE:
            continue
        if vote >= DISAGREE_POSITIVE:
            pos.append((agent, vote))
        elif vote <= DISAGREE_NEGATIVE:
            neg.append((agent, vote))
    return pos, neg


def disagreement_v2(signals) -> list:
    """Contradiction messages, one per dimension in which a confident positive and a confident negative agent meet."""
    groups: dict = {}
    for agent, vote, confidence in _items(signals):
        if confidence < DISAGREE_CONFIDENCE:
            continue
        dimension = AGENT_DIMENSION.get(agent, agent)
        positive, negative = groups.setdefault(dimension, ([], []))
        if vote >= DISAGREE_POSITIVE:
            positive.append(agent)
        elif vote <= DISAGREE_NEGATIVE:
            negative.append(agent)
    return [
        f"high-confidence disagreement ({dimension}): positive={','.join(sorted(pos))} negative={','.join(sorted(neg))}"
        for dimension, (pos, neg) in sorted(groups.items()) if pos and neg
    ]


def cross_dimension_notes(signals, limit: int = 3) -> list:
    """Informational notes for confident opposite votes in *different* dimensions (never blocks a decision, shown in the UI)."""
    pos, neg = _confident_sides(_items(signals))
    notes = []
    for p_agent, p_vote in pos:
        for n_agent, n_vote in neg:
            if AGENT_DIMENSION.get(p_agent, p_agent) != AGENT_DIMENSION.get(n_agent, n_agent):
                notes.append(f"{p_agent} is positive ({p_vote:+.2f}) while {n_agent} is negative ({n_vote:+.2f}); "
                             f"they measure different things, so this is informational and does not block the decision")
    return notes[:limit]


# Owner decision 2026-11-02: a strongly negative risk agent (vote <= -0.7 with high confidence) caps the tier at ACCUMULATE
# (investment mode) / HOLD_OR_WATCH (conservative engine has no ACCUMULATE) instead of sending the stock to REVIEW.
SEVERE_RISK_VOTE = -0.7
SEVERE_RISK_CONFIDENCE = 0.65     # "high confidence"; the core risk agent emits 0.23 .. 0.82


def severe_risk(signals) -> bool:
    return any(agent == "risk" and vote <= SEVERE_RISK_VOTE and confidence >= SEVERE_RISK_CONFIDENCE
               for agent, vote, confidence in _items(signals))


# --- P1.7/P1.1 display (v2): confidence is shown with 3 decimals, more when rounding would hide the comparison -------------
def fmt_conf(value: float, reference: Optional[float] = None) -> str:
    """v1: 2 decimals (unchanged). v2: 3 decimals, and enough extra decimals that a value below ``reference`` never prints
    as equal to it ("0.55 below 0.55" was a display-rounding artefact, see docs/reference_NO_before.md)."""
    if not is_v2():
        return f"{value:.2f}"
    digits = 3
    if reference is not None and value != reference:
        while digits < 6 and f"{value:.{digits}f}" == f"{reference:.{digits}f}":
            digits += 1
    return f"{value:.{digits}f}"


def fmt_threshold(value: float) -> str:
    return f"{value:.3f}" if is_v2() else f"{value:.2f}"


# --- graded (not stepped) price freshness (v2) -----------------------------------------------------------------------------
# v1 (agents._freshness): age <= 3 d -> 1.0, <= 7 d -> 0.65, <= 30 d -> 0.25, else 0.05. A price that turns 3.01 days old
# costs 0.35 of freshness at once, i.e. 0.105 of the evidence multiplier (Equinor: confidence 0.552 -> 0.49). v2 keeps the
# same values at the old anchors and interpolates linearly between them. The separate hard gate (price older than 7 days
# = ``fresh_price`` missing = Evidence BLOCK) is NOT changed.
PRICE_FRESHNESS_ANCHORS = ((3.0, 1.0), (7.0, 0.65), (30.0, 0.25), (90.0, 0.05))


def graded_price_freshness(age_days: float) -> float:
    anchors = PRICE_FRESHNESS_ANCHORS
    if age_days <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if age_days <= x1:
            return y0 + (y1 - y0) * (age_days - x0) / (x1 - x0)
    return anchors[-1][1]
