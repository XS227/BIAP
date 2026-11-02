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


# --- P1.4 (v2): peer benchmark keeps peers with a possibly-newer or undated report, at a partial discount ----------------------
# v1 (freshness.filing_dimension) excludes such peers and drops the whole benchmark when more than 15 % are excluded; in
# the Norwegian quarterly window that is 100 % of peers (Equinor, Aker BP) and for Germany 73 % undated peers (SAP), so the
# comparison agent abstained although a usable sector median existed. v2 keeps those peers with their latest available
# report; the benchmark's freshness factor is 1 - PEER_DISCOUNT_MAX * (share of discounted peers), and the comparison agent
# multiplies its confidence by it. Hard exclusions (peer explicitly excluded, inputs older than the ceiling) still count
# towards the 15 % limit. PEER_DISCOUNT_MAX = 0.30 is my choice; owner to confirm.
PEER_DISCOUNT_MAX = 0.30


# --- P1.4b (v2): the comparison vote is linear in the P/E discount instead of a five-step ladder ---------------------------
# v1 gives 0 up to 15 % and then jumps to +-0.3/0.35, and cannot tell 30 % from 60 %. v2: vote = COMPARISON_SLOPE x discount
# (percent, positive = cheaper than the peer median), clamped to [COMPARISON_VOTE_MIN, COMPARISON_VOTE_MAX]. Slope 0.02 reaches
# the v1 cap +0.6 at a 30 % discount; the v1 premium cap -0.5 is reached at a 25 % premium. Owner-approved 2026-11-02.
COMPARISON_SLOPE = 0.02
COMPARISON_VOTE_MAX = 0.6
COMPARISON_VOTE_MIN = -0.5


def comparison_vote_v2(discount_pct: float) -> float:
    return round(max(COMPARISON_VOTE_MIN, min(COMPARISON_VOTE_MAX, COMPARISON_SLOPE * float(discount_pct))), 6)


# --- P1.5 (v2): a positive score blocked only by missing comparison evidence becomes a labelled HOLD_OR_WATCH ----------------
# Owner decision 2026-11-02: output HOLD_OR_WATCH (conservative engine only), with this qualifier; no new call category.
ABSTENTION_QUALIFIER = {
    "qualifier": "POSITIVE_RELATIVE_VALUATION_UNVERIFIED",
    "label": "Positive; relative valuation not confirmed",
    "labelFa": "مثبت، ارزش‌گذاری نسبی تأیید نشده",
}
_COMPARISON_REVIEW_PREFIXES = ("valuation benchmark unavailable", "peer benchmark available, but the comparison confidence", "sector peer group")


def comparison_only_review(review_reasons) -> bool:
    """True when every review reason of a BUY is about missing / too small comparison evidence (and there is at least one)."""
    reasons = [str(r) for r in (review_reasons or ())]
    return bool(reasons) and all(r.startswith(_COMPARISON_REVIEW_PREFIXES) for r in reasons)


# --- v2 SELL gate (investment mode): SELL needs the evidence a BUY needs ---------------------------------------------------------------
# Owner decision 2026-11-02 (revised): decision confidence >= 0.45, a negative risk vote and at least two non-risk agents with a negative
# vote; otherwise the tier is REDUCE with the qualifier below. (No bar on the comparison agent's confidence.)
SELL_MIN_CONFIDENCE = 0.45
SELL_CONFIRMING_AGENTS = ("fundamental", "quality", "forecast", "comparison")
SELL_MIN_NEGATIVE_AGENTS = 2
SELL_NEGATIVE_MARGIN = 0.0         # a vote counts as negative below -margin; 0.0 = "vote < 0" (production). 0.10 is only measured (tools/p1_12_*), not enabled
SELL_UNVERIFIED_QUALIFIER = {
    "qualifier": "NEGATIVE_MULTIFACTOR_UNCONFIRMED",
    "label": "Negative; multi-factor confirmation insufficient",
    "labelFa": "منفی، تأیید چندعاملی ناکافی",
}


# --- P1.9: name the gate that decided (or capped) a call -----------------------------------------------------------------------------
# Additive API field ``blockingGate`` = {code, label, labelFa, detail[, from, to]} or None when the call is the ranking's own top/bottom
# tier and nothing held it back. Pure presentation: it never changes a tier. Used by both engines (investment payload, conservative result).
BLOCKING_GATES = {
    "EVIDENCE_BLOCK": ("Evidence check failed (BLOCK)", "بررسی شواهد رد شد (BLOCK)"),
    "MIN_AGENTS": ("Too few agents with data", "تعداد عامل‌های دارای داده کافی نیست"),
    "DISTRESS_POSITIVE_BLOCK": ("Distress gate blocks a positive call", "دروازه ریسک ورشکستگی توصیه مثبت را مسدود کرد"),
    "CONFIDENCE_FLOOR": ("Confidence below the tier floor", "اطمینان زیر کف مجاز رتبه"),
    "AGENTS_DISAGREE": ("Agents in the same dimension disagree", "عامل‌های هم‌بُعد با هم مخالفند"),
    "RISK_CAP": ("Severe risk vote caps the call", "رأی ریسک شدید رتبه را محدود کرد"),
    "BUY_DOWNGRADE": ("A caution flag lowers BUY to ACCUMULATE", "یک پرچم احتیاط BUY را به ACCUMULATE کاهش داد"),
    "SELL_MULTIFACTOR": ("SELL needs risk plus two other negative agents", "SELL به ریسک و دست‌کم دو عامل منفی دیگر نیاز دارد"),
    "SELL_LOW_CONFIDENCE": ("SELL needs confidence of at least 0.45", "SELL به اطمینان دست‌کم ۰٫۴۵ نیاز دارد"),
    "BUY_THRESHOLD": ("Did not reach the BUY threshold", "به آستانه BUY نرسید"),
    "SELL_THRESHOLD": ("Did not reach the SELL threshold", "به آستانه SELL نرسید"),
    "COMPARISON_ABSTAINED": ("Peer comparison abstained", "مقایسه با رقبا ممتنع بود"),
    "AGENT8_GOVERNANCE": ("Agent 8 governance review", "بازبینی حاکمیتی عامل ۸"),
    "DISTRESS_GATE": ("Distress safety gate", "دروازه ایمنی ریسک ورشکستگی"),
    "LOW_LIQUIDITY": ("Low liquidity", "نقدشوندگی کم"),
    "LIQUIDITY_UNCONFIRMED": ("Liquidity unconfirmed", "نقدشوندگی تأیید نشده"),
}


def make_gate(code: str, detail: str = "", **extra) -> dict:
    label, label_fa = BLOCKING_GATES[code]
    return {"code": code, "label": label, "labelFa": label_fa, "detail": detail, **extra}


_BLOCKED_PREFIX = (("evidence", "EVIDENCE_BLOCK"), ("only ", "MIN_AGENTS"), ("distress", "DISTRESS_POSITIVE_BLOCK"))


def investment_blocking_gate(call, blocked_by, flags, tier_before, score, soft_flags=()) -> Optional[dict]:
    """Gate for one investment-mode decision (fields of ``InvestmentDecision``)."""
    flags = list(flags or ())
    if blocked_by:
        code = next((c for p, c in _BLOCKED_PREFIX if str(blocked_by).startswith(p)), "EVIDENCE_BLOCK")
        return make_gate(code, str(blocked_by))
    if "low_liquidity" in flags:                                    # P1.12 (v2): tradability gate, BUY / ACCUMULATE -> HOLD
        return make_gate("LOW_LIQUIDITY", f"median-proxy daily traded value below USD {LIQUIDITY_MIN_USD:,.0f}; capped at HOLD",
                         **{"from": tier_before or "BUY", "to": call})
    if "liquidity_unconfirmed" in flags and tier_before == "BUY" and call == "ACCUMULATE":
        return make_gate("LIQUIDITY_UNCONFIRMED", "no usable volume/price/FX to confirm tradability; BUY limited to ACCUMULATE",
                         **{"from": "BUY", "to": "ACCUMULATE"})
    if "insufficient_evidence" in flags:
        return make_gate("CONFIDENCE_FLOOR", "decision confidence is below the BUY / ACCUMULATE floor; capped at HOLD",
                         **{"from": tier_before or "BUY", "to": call})
    if tier_before == "SELL" and call == "REDUCE":
        for flag, code in (("negative_multifactor_unconfirmed", "SELL_MULTIFACTOR"), ("sell_low_confidence", "SELL_LOW_CONFIDENCE"),
                           ("agents_disagree", "AGENTS_DISAGREE")):
            if flag in flags:
                return make_gate(code, flag, **{"from": "SELL", "to": "REDUCE"})
    if tier_before == "BUY" and call == "ACCUMULATE":
        if "risk_cap" in flags:
            return make_gate("RISK_CAP", "risk_cap", **{"from": "BUY", "to": "ACCUMULATE"})
        flag = next((f for f in flags if f in soft_flags), None)
        if flag == "agents_disagree":
            return make_gate("AGENTS_DISAGREE", flag, **{"from": "BUY", "to": "ACCUMULATE"})
        return make_gate("BUY_DOWNGRADE", flag or "", **{"from": "BUY", "to": "ACCUMULATE"})
    if call in ("HOLD", "ACCUMULATE"):
        return make_gate("BUY_THRESHOLD", "rank or score below the BUY cut-off")
    if call == "REDUCE":
        return make_gate("SELL_THRESHOLD", "rank or score above the SELL cut-off")
    return None


def conservative_blocking_gate(result) -> Optional[dict]:
    """Gate for a conservative-engine result dict (``analyze_company`` output)."""
    call = result.get("call")
    if call == "BUY_CANDIDATE":
        return None
    integrity = result.get("decisionIntegrity") or {}
    if result.get("abstentionCap"):
        return make_gate("COMPARISON_ABSTAINED", "; ".join(map(str, result["abstentionCap"].get("reasons") or ())),
                         **{"from": "BUY_CANDIDATE", "to": call})
    if result.get("riskCap"):
        return make_gate("RISK_CAP", str(result["riskCap"].get("reason") or ""), **{"from": "BUY_CANDIDATE", "to": call})
    if integrity.get("distressGateApplied"):
        return make_gate("DISTRESS_GATE", "Agent 9 distress positive_block")
    gov = result.get("governance") or {}
    if integrity.get("governanceAction") not in (None, "ACCEPT") or gov.get("review_reasons"):
        return make_gate("AGENT8_GOVERNANCE", "; ".join(map(str, gov.get("review_reasons") or ())) or str(integrity.get("governanceAction")))
    if call in ("HOLD_OR_WATCH", "NO_RECOMMENDATION", None):
        return make_gate("BUY_THRESHOLD", "score or confidence below the BUY candidate floor")
    return None


# ---- P1.12 (v2): liquidity is a tradability gate, not a directional vote -------------------------------------------------------
LIQUIDITY_MIN_USD = 100_000.0                   # daily traded value (USD, ECB rate) under this caps BUY / ACCUMULATE at HOLD
LIQUIDITY_GATE_EXEMPT_COUNTRIES: frozenset = frozenset()     # DE enabled 2026-11-02 after the Xetra volume check (P2.1); empty = every market
_MINOR_UNITS = {"GBX": ("GBP", 100.0), "GBPX": ("GBP", 100.0)}


def liquidity_gate_active(exchange: str) -> bool:
    """The gate runs under v2 for every market except those still awaiting a verified volume field."""
    country = str(exchange or "").split(":", 1)[0].upper()
    return is_v2() and country not in LIQUIDITY_GATE_EXEMPT_COUNTRIES


def daily_value_usd(*, price, avg_volume, currency, on, fx) -> Optional[float]:
    """Average 30-day daily traded value (price x average volume) in USD at the ECB reference rate of ``on``; ``None`` = unknown.

    The stored company carries only the 30-day *average* volume, not a daily series, so this is a mean-based proxy for the
    median value (a mean is >= the median for the usual right-skewed volume, so the gate is on the lenient side).
    """
    try:
        price, avg_volume = float(price), float(avg_volume)
        if not (price > 0 and avg_volume > 0):
            return None
        from datetime import date
        day = date.fromisoformat(str(on)[:10])
        code = str(currency or "").strip().upper()
        divisor = 1.0
        if code in _MINOR_UNITS:
            code, divisor = _MINOR_UNITS[code][0], _MINOR_UNITS[code][1]
        rate = float(fx.rate(code, "USD", day).rate)
        return price * avg_volume / divisor * rate
    except Exception:                                      # noqa: BLE001 - any missing input / rate means "unknown", never a guess
        return None
