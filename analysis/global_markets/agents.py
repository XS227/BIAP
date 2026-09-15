"""New BIAP Global agents.

EvidenceAgent is deliberately conservative: it can WARN or BLOCK when source
coverage/freshness is insufficient or when high-confidence analysis signals
materially disagree.

PortfolioAgent only allocates candidates that survive the evidence gate. It is
intended for research/paper portfolios first; it does not place orders.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from typing import Iterable, Mapping, Optional

from .models import (
    AgentSignal,
    EvidenceAssessment,
    GlobalCompany,
    InvestorProfile,
    PortfolioAllocation,
    PortfolioProposal,
    utc_now_iso,
)


_EVIDENCE_FIELDS = (
    "price",
    "market_cap",
    "price_52w_high",
    "price_52w_low",
    "volatility_annualized_pct",
    "pe",
    "revenue",
    "revenue_yoy_pct",
    "net_income",
    "net_margin_pct",
    "total_assets",
    "total_liabilities",
    "operating_cash_flow",
    "free_cash_flow",
    "total_debt",
)


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness(company: GlobalCompany, *, now: Optional[datetime] = None) -> tuple[float, Optional[float]]:
    observed = _parse_time(company.price_observed_at)
    if observed is None:
        return 0.35, None
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_days = max(0.0, (now - observed).total_seconds() / 86400.0)
    if age_days <= 3:
        return 1.0, age_days
    if age_days <= 7:
        return 0.75, age_days
    if age_days <= 30:
        return 0.4, age_days
    return 0.1, age_days


def evidence_agent(
    company: GlobalCompany,
    signals: Iterable[AgentSignal] = (),
    *,
    now: Optional[datetime] = None,
) -> EvidenceAssessment:
    """Assess whether the evidence is strong enough to support a decision."""

    missing_critical: list[str] = []
    if not company.country:
        missing_critical.append("country")
    if not company.exchange:
        missing_critical.append("exchange")
    if not company.ticker:
        missing_critical.append("ticker")
    if company.price is None or company.price <= 0:
        missing_critical.append("verified_price")
    if not company.sources:
        missing_critical.append("source_provenance")

    available = sum(getattr(company, field) is not None for field in _EVIDENCE_FIELDS)
    coverage = available / len(_EVIDENCE_FIELDS)
    freshness_score, price_age_days = _freshness(company, now=now)

    contradictions: list[str] = []
    confident_positive: list[str] = []
    confident_negative: list[str] = []
    for signal in signals:
        if signal.confidence < 0.55:
            continue
        if signal.vote >= 0.35:
            confident_positive.append(signal.agent)
        elif signal.vote <= -0.35:
            confident_negative.append(signal.agent)
    if confident_positive and confident_negative:
        contradictions.append(
            "high-confidence disagreement: positive="
            + ",".join(sorted(confident_positive))
            + " negative="
            + ",".join(sorted(confident_negative))
        )

    if price_age_days is not None and price_age_days > 30:
        missing_critical.append("fresh_price")

    quality_scores = [max(0.0, min(1.0, source.quality)) for source in company.sources]
    source_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    confidence_multiplier = max(
        0.0,
        min(1.0, (0.50 * coverage) + (0.30 * freshness_score) + (0.20 * source_quality)),
    )
    if contradictions:
        confidence_multiplier *= 0.75

    if missing_critical:
        status = "BLOCK"
    elif coverage < 0.35 or freshness_score < 0.5 or contradictions:
        status = "WARN"
    else:
        status = "PASS"

    reasons = [
        f"coverage={coverage:.0%}",
        f"freshness={freshness_score:.2f}",
        f"sourceQuality={source_quality:.2f}",
    ]
    if price_age_days is None:
        reasons.append("price timestamp unavailable")
    else:
        reasons.append(f"priceAgeDays={price_age_days:.1f}")
    if missing_critical:
        reasons.append("missing=" + ",".join(missing_critical))
    if contradictions:
        reasons.extend(contradictions)

    return EvidenceAssessment(
        status=status,
        confidence_multiplier=confidence_multiplier,
        coverage=coverage,
        freshness_score=freshness_score,
        contradictions=tuple(contradictions),
        missing_critical=tuple(missing_critical),
        reasoning="; ".join(reasons),
    )


@dataclass(frozen=True)
class PortfolioCandidate:
    company: GlobalCompany
    signals: tuple[AgentSignal, ...]
    evidence: EvidenceAssessment


def _candidate_score(candidate: PortfolioCandidate) -> tuple[float, float]:
    weighted = 0.0
    confidence_total = 0.0
    for signal in candidate.signals:
        confidence = max(0.0, min(1.0, signal.confidence))
        vote = max(-1.0, min(1.0, signal.vote))
        weighted += vote * confidence
        confidence_total += confidence
    if confidence_total <= 0:
        return 0.0, 0.0
    raw_score = weighted / confidence_total
    mean_confidence = confidence_total / max(1, len(candidate.signals))
    final_confidence = mean_confidence * candidate.evidence.confidence_multiplier
    return raw_score * candidate.evidence.confidence_multiplier, final_confidence


def _risk_penalty(company: GlobalCompany, risk_tolerance: str) -> float:
    tolerance = risk_tolerance.strip().lower()
    volatility = company.volatility_annualized_pct
    drawdown = company.max_drawdown_pct
    penalty = 0.0
    if volatility is not None:
        if tolerance in {"low", "conservative"} and volatility > 30:
            penalty += min(0.45, (volatility - 30) / 100)
        elif tolerance in {"medium", "moderate"} and volatility > 45:
            penalty += min(0.30, (volatility - 45) / 120)
    if drawdown is not None:
        magnitude = abs(drawdown)
        if tolerance in {"low", "conservative"} and magnitude > 25:
            penalty += min(0.35, (magnitude - 25) / 100)
        elif tolerance in {"medium", "moderate"} and magnitude > 40:
            penalty += min(0.20, (magnitude - 40) / 120)
    return min(0.7, penalty)


def portfolio_agent(
    profile: InvestorProfile,
    candidates: Iterable[PortfolioCandidate],
    *,
    fx_to_base: Optional[Mapping[str, float]] = None,
    min_score: float = 0.15,
    min_confidence: float = 0.35,
) -> PortfolioProposal:
    """Build a capped, diversified paper portfolio proposal.

    `fx_to_base` maps one unit of an instrument's quote currency to the investor's
    base currency. Missing FX does not fabricate a quantity; the allocation can
    still be expressed in base-currency budget terms with quantity=None.
    """

    if profile.capital <= 0:
        return PortfolioProposal(
            status="NO_RECOMMENDATION",
            generated_at=utc_now_iso(),
            invested_pct=0.0,
            cash_pct=100.0,
            allocations=(),
            reasoning="capital must be positive",
        )

    allowed_countries = {x.upper() for x in profile.allowed_countries}
    allowed_exchanges = {x.upper() for x in profile.allowed_exchanges}
    scored: list[tuple[PortfolioCandidate, float, float]] = []
    excluded: list[str] = []

    for candidate in candidates:
        company = candidate.company
        identity = company.identity()
        if candidate.evidence.blocked:
            excluded.append(f"{identity}: evidence blocked ({candidate.evidence.reasoning})")
            continue
        if allowed_countries and company.country.upper() not in allowed_countries:
            excluded.append(f"{identity}: country outside investor scope")
            continue
        if allowed_exchanges and company.exchange.upper() not in allowed_exchanges:
            excluded.append(f"{identity}: exchange outside investor scope")
            continue

        score, confidence = _candidate_score(candidate)
        score -= _risk_penalty(company, profile.risk_tolerance)
        if score < min_score or confidence < min_confidence:
            excluded.append(
                f"{identity}: below decision threshold score={score:.3f} confidence={confidence:.3f}"
            )
            continue
        scored.append((candidate, score, confidence))

    scored.sort(key=lambda item: (item[1] * item[2], item[2], item[1]), reverse=True)
    scored = scored[: max(0, profile.max_positions)]
    if not scored:
        return PortfolioProposal(
            status="NO_RECOMMENDATION",
            generated_at=utc_now_iso(),
            invested_pct=0.0,
            cash_pct=100.0,
            allocations=(),
            excluded=tuple(excluded),
            reasoning="no candidate cleared evidence, scope, risk and confidence gates",
        )

    investable_pct = max(0.0, min(100.0, 100.0 - profile.min_cash_reserve_pct))
    desirabilities = [max(0.001, score * confidence) for _, score, confidence in scored]
    desirability_total = sum(desirabilities)

    country_used: defaultdict[str, float] = defaultdict(float)
    sector_used: defaultdict[str, float] = defaultdict(float)
    allocations: list[PortfolioAllocation] = []
    allocated_pct = 0.0
    fx_to_base = {k.upper(): v for k, v in (fx_to_base or {}).items()}
    fx_to_base.setdefault(profile.base_currency.upper(), 1.0)

    for (candidate, score, confidence), desirability in zip(scored, desirabilities):
        company = candidate.company
        proposed = investable_pct * desirability / desirability_total
        room_position = max(0.0, profile.max_position_pct)
        room_country = max(0.0, profile.max_country_pct - country_used[company.country.upper()])
        sector_key = (company.sector or "UNKNOWN").upper()
        room_sector = max(0.0, profile.max_sector_pct - sector_used[sector_key])
        remaining = max(0.0, investable_pct - allocated_pct)
        weight = min(proposed, room_position, room_country, room_sector, remaining)
        if weight <= 0.01:
            excluded.append(f"{company.identity()}: diversification/concentration cap")
            continue

        amount_base = profile.capital * weight / 100.0
        fx_rate = fx_to_base.get(company.currency.upper())
        quantity: Optional[int] = None
        if fx_rate is not None and fx_rate > 0 and company.price is not None and company.price > 0:
            per_share_base = company.price * fx_rate
            quantity = floor(amount_base / per_share_base)
            if quantity <= 0:
                quantity = None

        allocation = PortfolioAllocation(
            identity=company.identity(),
            ticker=company.ticker,
            country=company.country,
            exchange=company.exchange,
            currency=company.currency,
            weight_pct=round(weight, 4),
            amount_base_currency=round(amount_base, 2),
            quantity=quantity,
            estimated_price=company.price,
            score=round(score, 4),
            confidence=round(confidence, 4),
            reasoning=(
                f"evidence={candidate.evidence.status}; "
                f"evidenceCoverage={candidate.evidence.coverage:.0%}; "
                f"score={score:.3f}; confidence={confidence:.3f}"
            ),
        )
        allocations.append(allocation)
        allocated_pct += weight
        country_used[company.country.upper()] += weight
        sector_used[sector_key] += weight

    if not allocations:
        return PortfolioProposal(
            status="NO_RECOMMENDATION",
            generated_at=utc_now_iso(),
            invested_pct=0.0,
            cash_pct=100.0,
            allocations=(),
            excluded=tuple(excluded),
            reasoning="eligible candidates could not be allocated within portfolio caps",
        )

    allocated_pct = min(100.0, allocated_pct)
    return PortfolioProposal(
        status="PAPER_PROPOSAL",
        generated_at=utc_now_iso(),
        invested_pct=round(allocated_pct, 4),
        cash_pct=round(100.0 - allocated_pct, 4),
        allocations=tuple(allocations),
        excluded=tuple(excluded),
        reasoning="paper proposal only; no broker order was submitted",
    )
