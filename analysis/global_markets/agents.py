"""BIAP Global verification and portfolio agents.

EvidenceAgent is deliberately conservative: it can WARN or BLOCK when source
coverage/freshness is insufficient. High-confidence disagreement between
analysis agents is recorded for Decision Governance, but does not downgrade the
quality of otherwise verified evidence. PortfolioAgent only allocates candidates
that survive the evidence gate and have verified FX/price information. It never
places orders.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import floor
from typing import Iterable, Mapping, Optional

from .decision_support import preference_adjustment
from .evidence_contract import official_fundamental_sources, official_fundamental_status
from .models import (
    AgentSignal,
    DistressAssessment,
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
    "total_equity",
    "operating_cash_flow",
    "free_cash_flow",
    "total_debt",
)

_MARKET_SOURCE_TOKENS = ("market", "price", "quote", "history")
_FUNDAMENTAL_SOURCE_TOKENS = ("filing", "regulatory", "xbrl", "fundamental", "financial_statement")
_SECONDARY_FUNDAMENTAL_SOURCE_TOKENS = ("public_vendor_financial_metrics",)
_VERIFIED_SOURCE_TOKENS = (
    "official", "regulatory", "xbrl", "filing", "exchange", "sec", "edgar",
    "esef", "edinet", "opendart", "issuer", "companies_house",
)


def _source_provenance(source) -> str:
    explicit = str(getattr(source, "provenance_status", "") or "").strip().lower()
    if explicit and explicit != "unknown":
        return explicit
    text = f"{source.provider} {source.source_type}".lower().replace("-", "_")
    if source.provider == "biap-derived-metrics" or "derived_" in text:
        return "derived"
    if "manual" in text or "user_entered" in text:
        return "user_entered"
    if any(token in text for token in _VERIFIED_SOURCE_TOKENS) and (source.source_id or source.source_url or "official" in text or "regulatory" in text):
        return "independently_verified"
    if source.source_id or source.source_url:
        return "cited_source"
    return "source_supplied"


def _aggregate_provenance(company: GlobalCompany) -> str:
    values = [_source_provenance(source) for source in company.sources]
    values = [value for value in values if value != "derived"]
    if not values:
        return "unknown"
    if "independently_verified" in values:
        return "independently_verified"
    if "cited_source" in values:
        return "cited_source"
    if "user_entered" in values:
        return "user_entered"
    return "source_supplied"


def _aggregate_audit_status(company: GlobalCompany) -> str:
    explicit = [str(getattr(source, "audit_status", "") or "").strip().lower() for source in company.sources]
    if "audited" in explicit:
        return "audited"
    if "unaudited" in explicit:
        return "unaudited"
    opinion = (company.audit_opinion or "").strip().lower()
    audited_markers = ("unqualified", "qualified", "adverse", "disclaimer")
    if opinion and "unaudited" not in opinion and any(marker in opinion for marker in audited_markers):
        return "audited"
    if "unaudited" in opinion:
        return "unaudited"
    return "unknown"


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
        return 0.25, None
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_days = max(0.0, (now - observed).total_seconds() / 86400.0)
    if age_days <= 3:
        return 1.0, age_days
    if age_days <= 7:
        return 0.65, age_days
    if age_days <= 30:
        return 0.25, age_days
    return 0.05, age_days


def _fundamental_freshness(
    company: GlobalCompany,
    *,
    now: Optional[datetime] = None,
) -> tuple[float, Optional[float]]:
    """Score the reporting period separately from the market-price timestamp.

    A newly observed/cached source must not make an old reporting period look
    fresh.  The 550-day hard limit allows normal annual-report publication
    calendars while rejecting statements that are more than one fiscal cycle
    behind.
    """

    value = (company.filing_period_end or "").strip()[:10]
    if not value:
        # Some official exchange annual datasets (notably Börse Frankfurt
        # historical key data) publish a fiscal/report year but no exact period
        # end. Do not invent a calendar date. Treat the latest prior fiscal year
        # as current annual evidence, while keeping older years conservative.
        raw = company.raw_provider_fields or {}
        if raw.get("de_bf_historical_key_data") and raw.get("de_bf_period_granularity") == "year_only":
            try:
                report_year = int(raw.get("de_bf_report_year"))
            except (TypeError, ValueError):
                report_year = 0
            current_year = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).year
            if report_year >= current_year - 1:
                return 1.0, None
            if report_year == current_year - 2:
                return 0.25, None
            if report_year > 0:
                return 0.05, None
        return 0.25, None
    try:
        period_end = date.fromisoformat(value)
    except ValueError:
        return 0.0, None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    age_days = float(max(0, (current - period_end).days))
    if age_days <= 450:
        return 1.0, age_days
    if age_days <= 550:
        return 0.65, age_days
    if age_days <= 730:
        return 0.25, age_days
    return 0.05, age_days


def _has_source_type(company: GlobalCompany, tokens: tuple[str, ...]) -> bool:
    for source in company.sources:
        kind = source.source_type.lower().replace("-", "_")
        if any(token in kind for token in tokens):
            return True
    return False


def evidence_agent(
    company: GlobalCompany,
    signals: Iterable[AgentSignal] = (),
    *,
    now: Optional[datetime] = None,
) -> EvidenceAssessment:
    """Assess whether evidence is strong enough to support a decision.

    A verified price alone is insufficient for a directional investment call.
    BIAP Global requires both market provenance and official/verified fundamental
    provenance. Missing sources lead to BLOCK rather than model guesswork.
    """

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
    if not _has_source_type(company, _MARKET_SOURCE_TOKENS):
        missing_critical.append("market_source")
    # Canonical contract: official filings remain the only evidence that can
    # clear the gate to PASS. Germany has a long tail of valid listed issuers
    # whose issuer/Company-Register reports are not machine-resolvable by BIAP
    # yet. For those DE listings only, a cited public-vendor fundamentals
    # snapshot may keep the analysis usable as WARN, but never as PASS.
    # Governance separately forces every WARN to NO_RECOMMENDATION.
    official_sources = official_fundamental_sources(company)
    secondary_fundamental_source = _has_source_type(
        company, _SECONDARY_FUNDAMENTAL_SOURCE_TOKENS
    )
    secondary_core_fields = (
        "revenue", "net_income", "total_assets", "total_liabilities", "total_equity",
    )
    secondary_core_coverage = sum(
        getattr(company, field) is not None for field in secondary_core_fields
    )
    secondary_only_fundamentals = (
        not official_sources
        and company.country.upper() == "DE"
        and secondary_fundamental_source
        and secondary_core_coverage >= 4
    )
    if not official_sources and not secondary_only_fundamentals:
        missing_critical.append("fundamental_source")
    official_status, official_detail = official_fundamental_status(company, now=now)

    available = sum(getattr(company, field) is not None for field in _EVIDENCE_FIELDS)
    coverage = available / len(_EVIDENCE_FIELDS)
    price_freshness, price_age_days = _freshness(company, now=now)
    fundamental_freshness, fundamental_age_days = _fundamental_freshness(company, now=now)
    freshness_score = min(price_freshness, fundamental_freshness)

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

    # More than one trading week old is not acceptable as a current price for
    # a new portfolio proposal. The analysis can still be shown as blocked.
    if price_age_days is not None and price_age_days > 7:
        missing_critical.append("fresh_price")
    if company.filing_period_end and fundamental_age_days is None:
        missing_critical.append("valid_fundamental_period")
    elif fundamental_age_days is not None and fundamental_age_days > 550:
        missing_critical.append("fresh_fundamentals")

    provenance_status = _aggregate_provenance(company)
    audit_status = _aggregate_audit_status(company)
    quality_scores = [
        max(0.0, min(1.0, source.quality))
        for source in company.sources
        if _source_provenance(source) != "derived"
    ]
    source_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    confidence_multiplier = max(
        0.0,
        min(1.0, (0.45 * coverage) + (0.30 * freshness_score) + (0.25 * source_quality)),
    )
    # Agent disagreement is a decision/governance concern, not an evidence-
    # quality defect. Preserve it in EvidenceAssessment.contradictions so the
    # governance layer can force REVIEW, but do not lower evidence confidence.
    if secondary_only_fundamentals:
        # Secondary fundamentals are useful for research but cannot inherit
        # the confidence of audited/official issuer evidence.
        confidence_multiplier = min(confidence_multiplier, 0.50)
    if provenance_status == "user_entered":
        # Manual input may be useful for research, but it is not independent
        # verification and cannot silently inherit an "audited" label.
        confidence_multiplier *= 0.70
    if missing_critical:
        confidence_multiplier = min(confidence_multiplier, 0.20)

    if missing_critical:
        status = "BLOCK"
    elif (
        secondary_only_fundamentals
        or coverage < 0.35
        or freshness_score < 0.65
        or provenance_status == "user_entered"
    ):
        status = "WARN"
    else:
        status = "PASS"

    reasons = [
        f"coverage={coverage:.0%}",
        f"freshness={freshness_score:.2f}",
        f"sourceQuality={source_quality:.2f}",
        f"provenance={provenance_status}",
        f"auditStatus={audit_status}",
    ]
    if price_age_days is None:
        reasons.append("price timestamp unavailable")
    else:
        reasons.append(f"priceAgeDays={price_age_days:.1f}")
    if fundamental_age_days is None:
        reasons.append("fundamentalPeriodAgeDays=unavailable")
    else:
        reasons.append(f"fundamentalPeriodAgeDays={fundamental_age_days:.1f}")
    if secondary_only_fundamentals:
        reasons.append("fundamentalProvenance=secondary_only_no_official_filing")
    if missing_critical:
        reasons.append("missing=" + ",".join(dict.fromkeys(missing_critical)))
    reasons.append(f"officialFundamentals={official_status} ({official_detail})")
    if contradictions:
        reasons.extend(contradictions)

    return EvidenceAssessment(
        status=status,
        confidence_multiplier=confidence_multiplier,
        coverage=coverage,
        freshness_score=freshness_score,
        contradictions=tuple(contradictions),
        missing_critical=tuple(dict.fromkeys(missing_critical)),
        source_quality_score=source_quality,
        provenance_status=provenance_status,
        audit_status=audit_status,
        reasoning="; ".join(reasons),
        official_fundamental_status=official_status,
        official_fundamental_detail=official_detail,
    )


@dataclass(frozen=True)
class PortfolioCandidate:
    company: GlobalCompany
    signals: tuple[AgentSignal, ...]
    evidence: EvidenceAssessment
    distress: Optional[DistressAssessment] = None


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

    `fx_to_base` maps one unit of an instrument quote currency to the investor
    base currency. A cross-currency candidate without verified FX is excluded.
    Lot sizes are respected when known. No order is sent to a broker.
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
    normalized_fx = {k.upper(): float(v) for k, v in (fx_to_base or {}).items() if float(v) > 0}
    normalized_fx.setdefault(profile.base_currency.upper(), 1.0)

    scored: list[tuple[PortfolioCandidate, float, float]] = []
    excluded: list[str] = []

    for candidate in candidates:
        company = candidate.company
        identity = company.identity()
        if candidate.evidence.blocked:
            excluded.append(f"{identity}: evidence blocked ({candidate.evidence.reasoning})")
            continue
        if candidate.distress is not None and candidate.distress.positive_block:
            excluded.append(f"{identity}: distress safety gate ({candidate.distress.reasoning})")
            continue
        if allowed_countries and company.country.upper() not in allowed_countries:
            excluded.append(f"{identity}: country outside investor scope")
            continue
        if allowed_exchanges and company.exchange.upper() not in allowed_exchanges:
            excluded.append(f"{identity}: exchange outside investor scope")
            continue
        if company.currency.upper() not in normalized_fx:
            excluded.append(f"{identity}: verified FX to {profile.base_currency.upper()} unavailable")
            continue
        if company.price is None or company.price <= 0:
            excluded.append(f"{identity}: verified positive price unavailable")
            continue

        score, confidence = _candidate_score(candidate)
        score -= _risk_penalty(company, profile.risk_tolerance)
        suitability_adjustment = preference_adjustment(company, profile)
        score += suitability_adjustment
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
            reasoning="no candidate cleared evidence, scope, FX, risk and confidence gates",
        )

    investable_pct = max(0.0, min(100.0, 100.0 - profile.min_cash_reserve_pct))
    desirabilities = [max(0.001, score * confidence) for _, score, confidence in scored]
    desirability_total = sum(desirabilities)

    country_used: defaultdict[str, float] = defaultdict(float)
    sector_used: defaultdict[str, float] = defaultdict(float)
    allocations: list[PortfolioAllocation] = []
    allocated_pct = 0.0

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
        fx_rate = normalized_fx[company.currency.upper()]
        per_share_base = company.price * fx_rate
        if per_share_base <= 0:
            excluded.append(f"{company.identity()}: invalid converted share price")
            continue
        raw_quantity = floor(amount_base / per_share_base)
        lot_size = max(1, int(company.lot_size or 1))
        quantity = (raw_quantity // lot_size) * lot_size
        if quantity <= 0:
            excluded.append(f"{company.identity()}: allocation cannot buy one minimum lot")
            continue

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
                f"score={score:.3f}; confidence={confidence:.3f}; "
                f"profileFitAdjustment={preference_adjustment(company, profile):+.3f}; "
                f"fx={fx_rate:.8g}; lot={lot_size}"
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
            reasoning="eligible candidates could not be allocated within portfolio/lot constraints",
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
