"""Investment-opportunity classification, separate from the Qualified BUY gate.

Agent 8 (governance) decides whether a draft call may be *accepted*; it turns
every non-accepted draft, including the non-directional HOLD_OR_WATCH, into
NO_RECOMMENDATION. That is correct as a safety gate but hides the underlying
assessment. This module exposes it without touching any gate:

* BUY            - qualified: draft BUY_CANDIDATE accepted by Agent 8 (unchanged).
* WATCH          - potentially attractive, BUY conditions not satisfied.
* REVIEW         - attractive-looking or unclear, needs further investigation.
* HIGH_RISK      - evidence supports significant risk (negative evidence-backed
                   score, or Agent 9 HIGH_RISK computed from real inputs).
* INSUFFICIENT_DATA - a reliable assessment cannot be completed.

Financial distress stays a separate axis: missing debt/EBITDA yields an
INSUFFICIENT_DATA *distress* status, never HIGH_RISK, and never by itself an
INSUFFICIENT_DATA investment state.
"""
from __future__ import annotations

from typing import Optional

BUY = "BUY"
WATCH = "WATCH"
REVIEW = "REVIEW"
HIGH_RISK = "HIGH_RISK"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

STATE_ORDER = {BUY: 0, WATCH: 1, REVIEW: 2, HIGH_RISK: 3, INSUFFICIENT_DATA: 4}

# Watch threshold is deliberately below the BUY score gate (0.25): a name that
# scores positively with usable confidence deserves monitoring.
WATCH_MIN_SCORE = 0.10
MIN_ASSESSABLE_CONFIDENCE = 0.35
MIN_WATCH_CONFIDENCE = 0.45

# Root-cause categories for a non-BUY outcome.
MISSING_DATA = "MISSING_DATA"
VALUATION = "UNATTRACTIVE_VALUATION"
FUNDAMENTALS = "WEAK_FUNDAMENTALS"
DISTRESS = "ELEVATED_DISTRESS_RISK"
MOMENTUM = "NEGATIVE_MOMENTUM_OR_VOLATILITY"
GOVERNANCE = "GOVERNANCE_RESTRICTION"
NEUTRAL = "NEUTRAL_NO_EDGE"


def _signal_votes(signals) -> dict[str, tuple[float, float]]:
    votes: dict[str, tuple[float, float]] = {}
    for item in signals or ():
        if isinstance(item, dict):
            name, vote, conf = item.get("agent"), item.get("vote"), item.get("confidence")
        else:
            name, vote, conf = item.agent, item.vote, item.confidence
        if name is not None and vote is not None:
            votes[str(name)] = (float(vote), float(conf or 0.0))
    return votes


def abstention_reasons(governance: dict, evidence: dict, distress: dict, *, preliminary_call: str,
                       confidence: float) -> list[dict]:
    """Structured reasons Agent 8 did not accept the draft (empty when accepted)."""
    if governance.get("accepted"):
        return []
    reasons: list[dict] = []
    for text in governance.get("hardBlocks") or governance.get("hard_blocks") or ():
        reasons.append({"code": "HARD_BLOCK", "kind": GOVERNANCE, "detail": str(text)})
    status = evidence.get("status")
    if status == "WARN":
        reasons.append({"code": "EVIDENCE_WARN", "kind": MISSING_DATA,
                        "detail": "Evidence gate WARN: research-grade only, never promoted to an actionable call"})
    if evidence.get("contradictions"):
        reasons.append({"code": "AGENT_DISAGREEMENT", "kind": GOVERNANCE,
                        "detail": "; ".join(map(str, evidence["contradictions"]))})
    if distress.get("status") == "ELEVATED_RISK" and status != "BLOCK":
        reasons.append({"code": "ELEVATED_DISTRESS", "kind": DISTRESS,
                        "detail": "Agent 9 reports elevated independent distress risk"})
    if preliminary_call == "HOLD_OR_WATCH" and not reasons:
        reasons.append({"code": "NON_DIRECTIONAL_BELOW_ACCEPT_THRESHOLD", "kind": GOVERNANCE,
                        "detail": f"Draft call HOLD_OR_WATCH is non-actionable; confidence {confidence:.2f} is below the "
                                  "0.55 accept threshold so Agent 8 reports NO_RECOMMENDATION"})
    elif confidence < 0.55 and not any(r["code"] == "HARD_BLOCK" for r in reasons):
        reasons.append({"code": "LOW_CONFIDENCE", "kind": GOVERNANCE,
                        "detail": f"Calibrated confidence {confidence:.2f} is below the 0.55 accept threshold"})
    if not reasons:
        reasons.append({"code": "GOVERNANCE_ABSTAIN", "kind": GOVERNANCE,
                        "detail": str(governance.get("reasoning") or "Agent 8 abstained")})
    return reasons


def limiting_factors(signals, metrics: Optional[dict], distress: dict) -> list[dict]:
    """Which axes hold the score down (most negative first). Informational only."""
    votes = _signal_votes(signals)
    mapping = {
        "fundamental": FUNDAMENTALS, "quality": FUNDAMENTALS, "comparison": VALUATION,
        "risk": MOMENTUM, "forecast": MOMENTUM, "liquidity": MISSING_DATA,
    }
    out = []
    for agent, (vote, conf) in votes.items():
        if vote < -0.05:
            out.append({"agent": agent, "vote": round(vote, 3), "kind": mapping.get(agent, FUNDAMENTALS)})
    out.sort(key=lambda item: item["vote"])
    ret6 = (metrics or {}).get("return6mPct")
    if ret6 is not None and ret6 < -15:
        out.append({"agent": "momentum", "vote": None, "kind": MOMENTUM,
                    "detail": f"6-month return {ret6:.1f}%"})
    if distress.get("status") in {"ELEVATED_RISK", "HIGH_RISK"}:
        out.append({"agent": "agent9", "vote": None, "kind": DISTRESS, "detail": distress.get("reasoning")})
    return out


def classify_opportunity(*, preliminary_call: str, final_call: str, score: float, confidence: float,
                         evidence: dict, distress: dict, governance: dict, signals=None,
                         metrics: Optional[dict] = None) -> dict:
    ev_status = evidence.get("status")
    dist_status = distress.get("status")
    models = list(distress.get("available_models") or distress.get("availableModels") or ())
    # One model alone (e.g. Zmijewski on a leveraged but investment-grade telco)
    # is a distress *finding* on the separate axis, not corroborated evidence of
    # an unattractive investment: route to REVIEW instead of HIGH_RISK.
    single_model_distress = dist_status == "HIGH_RISK" and len(models) == 1
    reasons = abstention_reasons(governance, evidence, distress,
                                 preliminary_call=preliminary_call, confidence=confidence)
    factors = limiting_factors(signals, metrics, distress)
    notes: list[str] = []

    if final_call == "BUY_CANDIDATE" and governance.get("accepted"):
        state, primary = BUY, None
        notes.append("Qualified BUY: score, confidence, PASS evidence and Agent 8 acceptance all satisfied.")
    elif final_call == "HOLD_OR_WATCH" and governance.get("accepted") and dist_status != "HIGH_RISK":
        state, primary = WATCH, GOVERNANCE
        notes.append("Agent 8 accepted a HOLD_OR_WATCH draft: keep monitoring; BUY conditions are not satisfied.")
    elif ev_status == "BLOCK" or confidence < MIN_ASSESSABLE_CONFIDENCE:
        state = INSUFFICIENT_DATA
        primary = MISSING_DATA
        missing = list(evidence.get("missingCritical") or evidence.get("missing_critical") or ())
        notes.append("Reliable assessment cannot be completed: "
                     + (f"missing {', '.join(missing)}" if missing else f"calibrated confidence {confidence:.2f} < {MIN_ASSESSABLE_CONFIDENCE}"))
    elif (dist_status == "HIGH_RISK" and not single_model_distress) or preliminary_call == "AVOID_OR_REVIEW":
        state = HIGH_RISK
        primary = DISTRESS if dist_status == "HIGH_RISK" else (factors[0]["kind"] if factors else FUNDAMENTALS)
        notes.append("Evidence supports significant risk"
                     + (" (Agent 9 HIGH_RISK from computed models)." if dist_status == "HIGH_RISK"
                        else f" (score {score:.2f} <= -0.25 at confidence >= 0.45)."))
    elif score >= WATCH_MIN_SCORE and confidence >= MIN_WATCH_CONFIDENCE:
        needs_review = (ev_status == "WARN" or bool(evidence.get("contradictions"))
                        or dist_status == "ELEVATED_RISK" or bool(distress.get("positiveBlock", distress.get("positive_block"))))
        state = REVIEW if needs_review else WATCH
        primary = (DISTRESS if dist_status == "ELEVATED_RISK" else MISSING_DATA if ev_status == "WARN"
                   else GOVERNANCE)
        notes.append("Positive score below the Qualified BUY standard; "
                     + ("an unresolved evidence/risk condition needs investigation." if needs_review
                        else "monitor for the missing BUY conditions."))
    else:
        state = REVIEW
        primary = DISTRESS if single_model_distress else (factors[0]["kind"] if factors else NEUTRAL)
        notes.append("Agent 9 HIGH_RISK rests on a single model (uncorroborated); investigate before concluding."
                     if single_model_distress else
                     "No clear edge: neutral or weakly positive score with limited confidence.")

    # Distress data gaps are reported on their own axis and never drive the state.
    distress_missing = dist_status == "INSUFFICIENT_DATA"
    if distress_missing:
        notes.append("Distress models could not run (missing debt/EBITDA/interest inputs); this is a data gap, "
                     "not a distress finding, and did not affect the state.")

    return {
        "state": state,
        "primaryCause": primary,
        "explanation": " ".join(notes),
        "underlying": {"draftCall": preliminary_call, "score": round(float(score), 4),
                       "confidence": round(float(confidence), 4)},
        "agent8Abstention": reasons,
        "limitingFactors": factors,
        "distressAxis": {"status": dist_status, "dataGap": distress_missing,
                         "missingInputs": list(distress.get("missingInputs") or distress.get("missing_inputs") or ())},
    }


def rank_opportunities(rows: list[dict], limit: int = 20) -> list[dict]:
    """Rank rows carrying an 'opportunity' dict: state first, then score x confidence.

    HIGH_RISK / INSUFFICIENT_DATA rows are never shown while any better row exists
    and are never padded in as positives; nothing is manufactured to fill the slots.
    """
    def key(row):
        opp = row["opportunity"]
        u = opp["underlying"]
        return (STATE_ORDER[opp["state"]], -(u["score"] * u["confidence"]))
    eligible = [
        r for r in rows
        if r["opportunity"]["state"] in (BUY, WATCH)
        or (r["opportunity"]["state"] == REVIEW and r["opportunity"]["underlying"]["score"] > 0)
    ]
    return sorted(eligible, key=key)[: max(0, int(limit))]


def opportunity_of(result: dict) -> dict:
    """Stored opportunity block, or one derived from the stored agent outputs."""
    if isinstance(result.get("opportunity"), dict):
        return result["opportunity"]
    integ = result.get("decisionIntegrity") or {}
    metrics = (result.get("decisionTable") or {}).get("metrics") or {}
    return classify_opportunity(
        preliminary_call=integ.get("preliminaryCall") or result.get("call") or "NO_RECOMMENDATION",
        final_call=result.get("call") or "NO_RECOMMENDATION",
        score=float(result.get("score") or 0.0), confidence=float(result.get("confidence") or 0.0),
        evidence=result.get("evidence") or {}, distress=result.get("distress") or {},
        governance=result.get("governance") or {}, signals=result.get("signals"),
        metrics={"return6mPct": metrics.get("return6mPct")})


def market_opportunities(results, limit: int = 20) -> dict:
    """Up to ``limit`` ranked opportunities (one row per issuer) plus state counts.

    Never padded: a market with fewer qualifying names returns fewer rows.
    """
    from .issuer import collapse_issuers

    rows, counts = [], {state: 0 for state in STATE_ORDER}
    for result in results:
        opp = opportunity_of(result)
        counts[opp["state"]] = counts.get(opp["state"], 0) + 1
        company = result.get("company") or {}
        rows.append({
            "ticker": result.get("ticker"), "name": result.get("name"), "isin": result.get("isin"),
            "lei": result.get("lei"), "country": result.get("country"), "exchange": result.get("exchange"), "call": result.get("call"), "score": result.get("score"),
            "confidence": result.get("confidence"), "opportunity": opp,
            "evidenceStatus": (result.get("evidence") or {}).get("status"),
            "distressStatus": (result.get("distress") or {}).get("status"),
            "priceObservedAt": company.get("price_observed_at"), "currency": company.get("currency"),
        })
    rank = lambda r: (-STATE_ORDER[r["opportunity"]["state"]], float(r["score"] or 0) * float(r["confidence"] or 0))
    ranked = rank_opportunities(rows, limit=len(rows))
    ranked = sorted(collapse_issuers(ranked, rank), key=rank, reverse=True)[: max(0, int(limit))]
    return {"stateCounts": counts, "analysed": len(rows), "ranked": [{**r, "rank": i} for i, r in enumerate(ranked, 1)],
            "note": "Opportunity ranking is separate from the Qualified BUY gate; no BUY is created or implied for WATCH/REVIEW rows."}
