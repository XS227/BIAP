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
from .issuer import resolve_issuer_identities
from .evidence_contract import freshness_tier, official_fundamental_sources, official_fundamental_status
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


def _official_core_figures(company: GlobalCompany) -> bool:
    """At least one P&L figure and two of revenue/net income/assets/equity."""
    core = ("revenue", "net_income", "total_assets", "total_equity")
    present = sum(getattr(company, field) is not None for field in core)
    return present >= 2 and (company.revenue is not None or company.net_income is not None)


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
    elif official_sources and not _official_core_figures(company):
        # An official source whose parsed statement lacks every P&L figure
        # (KAP AGHOL FY2025: only equity and current items were read) is a
        # parser gap, not evidence; it must not clear the gate.
        missing_critical.append("fundamental_core_figures")
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
    # OFFICIAL_CURRENT = newest official filing passed the staleness gate; the
    # tier says how recent that filing actually is.
    reasons.append(
        f"fundamentalFreshnessTier={freshness_tier(official_status, None if fundamental_age_days is None else int(fundamental_age_days))}"
    )
    reasons.append("note=evidence status describes data-quality gates only; it is not a buy/sell recommendation")
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
    rejections: list[dict] = []

    def reject(identity: str, constraint: str, text: str, **details) -> None:
        excluded.append(f"{identity}: {text}")
        rejections.append({"identity": identity, "constraint": constraint, **details})

    for candidate in candidates:
        company = candidate.company
        identity = company.identity()
        if candidate.evidence.blocked:
            reject(identity, "evidence_gate", f"evidence blocked ({candidate.evidence.reasoning})", missing=list(candidate.evidence.missing_critical))
            continue
        if candidate.distress is not None and candidate.distress.positive_block:
            reject(identity, "distress_gate", f"distress safety gate ({candidate.distress.reasoning})", status=candidate.distress.status)
            continue
        if allowed_countries and company.country.upper() not in allowed_countries:
            reject(identity, "allowed_countries", "country outside investor scope", value=company.country.upper(), allowed=sorted(allowed_countries))
            continue
        if allowed_exchanges and company.exchange.upper() not in allowed_exchanges:
            reject(identity, "allowed_exchanges", "exchange outside investor scope", value=company.exchange.upper(), allowed=sorted(allowed_exchanges))
            continue
        if company.currency.upper() not in normalized_fx:
            reject(identity, "fx_unavailable", f"verified FX to {profile.base_currency.upper()} unavailable", currency=company.currency.upper())
            continue
        if company.price is None or company.price <= 0:
            reject(identity, "price_unavailable", "verified positive price unavailable")
            continue

        score, confidence = _candidate_score(candidate)
        score -= _risk_penalty(company, profile.risk_tolerance)
        suitability_adjustment = preference_adjustment(company, profile)
        score += suitability_adjustment
        if score < min_score or confidence < min_confidence:
            reject(
                identity, "decision_threshold",
                f"below decision threshold score={score:.3f} (min {min_score}) "
                f"confidence={confidence:.3f} (min {min_confidence})",
                score=round(score, 4), min_score=min_score,
                confidence=round(confidence, 4), min_confidence=min_confidence,
            )
            continue
        scored.append((candidate, score, confidence))

    scored.sort(key=lambda item: (item[1] * item[2], item[2], item[1]), reverse=True)
    if not scored:
        return PortfolioProposal(
            status="NO_RECOMMENDATION",
            generated_at=utc_now_iso(),
            invested_pct=0.0,
            cash_pct=100.0,
            allocations=(),
            excluded=tuple(excluded),
            rejections=tuple(rejections),
            reasoning="no candidate cleared evidence, scope, FX, risk and confidence gates",
        )

    investable_pct = max(0.0, min(100.0, 100.0 - profile.min_cash_reserve_pct))
    max_positions = max(0, profile.max_positions)

    # One issuer = one position: keep the best-ranked listing of each issuer.
    # ASML (NASDAQ + Euronext Amsterdam) and GOOG/GOOGL are one issuer; `issuer`
    # is the validated LEI/CIK/ISIN identity (see issuer.py), never a loose name.
    issuers = resolve_issuer_identities([c.company for c, _, _ in scored])
    pool: list[tuple[PortfolioCandidate, float, float, str]] = []
    held_by: dict[str, str] = {}
    for (candidate, score, confidence), issuer in zip(scored, issuers):
        if issuer in held_by:
            identity = candidate.company.identity()
            excluded.append(f"{identity}: duplicate_issuer (issuer {issuer} is already held through {held_by[issuer]}, a better-ranked listing)")
            rejections.append({
                "identity": identity, "constraint": "duplicate_issuer", "limit": profile.max_position_pct,
                "room": 0.0, "issuer": issuer, "heldThrough": held_by[issuer],
            })
            continue
        held_by[issuer] = candidate.company.identity()
        pool.append((candidate, score, confidence, issuer))

    def fill(active: list[tuple[PortfolioCandidate, float, float, str]]) -> tuple[list[float], list[str]]:
        """Proportional-to-desirability weights in rank order, redistributing any
        weight a capped candidate cannot take to the candidates that still have room."""
        n = len(active)
        desirability = [max(0.001, sc * cf) for _, sc, cf, _ in active]
        weights = [0.0] * n
        binding = ["investable_cash"] * n
        country_used: defaultdict[str, float] = defaultdict(float)
        sector_used: defaultdict[str, float] = defaultdict(float)
        open_idx = list(range(n))
        remaining = investable_pct
        for _ in range(64):
            if remaining <= 1e-9 or not open_idx:
                break
            total = sum(desirability[i] for i in open_idx)
            budget = remaining
            moved = 0.0
            still_open: list[int] = []
            for i in open_idx:
                company = active[i][0].company
                country_key = company.country.upper()
                sector_key = (company.sector or "UNKNOWN").upper()
                rooms = (
                    ("max_position_pct", max(0.0, profile.max_position_pct) - weights[i]),
                    ("max_country_pct", max(0.0, profile.max_country_pct) - country_used[country_key]),
                    ("max_sector_pct", max(0.0, profile.max_sector_pct) - sector_used[sector_key]),
                    ("investable_cash", remaining),
                )
                name, room = min(rooms, key=lambda item: item[1])
                give = max(0.0, min(budget * desirability[i] / total, room))
                weights[i] += give
                country_used[country_key] += give
                sector_used[sector_key] += give
                remaining -= give
                moved += give
                binding[i] = name
                if room - give > 1e-9:
                    still_open.append(i)
            open_idx = still_open
            if moved <= 1e-9:
                break
        return weights, binding

    active = pool[:max_positions]
    waiting = pool[max_positions:]
    placed: list[tuple[tuple[PortfolioCandidate, float, float, str], float, int, str]] = []
    for _ in range(len(pool) + 2):
        if not active:
            placed = []
            break
        weights, binding = fill(active)
        failed: list[int] = []
        placed = []
        for i, entry in enumerate(active):
            candidate, score, confidence, issuer = entry
            company = candidate.company
            if weights[i] <= 0.01:
                excluded.append(
                    f"{company.identity()}: constraint {binding[i]} exhausted "
                    f"(no room left once better-ranked positions were sized; proposed {weights[i]:.2f}%)"
                )
                rejections.append({
                    "identity": company.identity(), "constraint": binding[i],
                    "limit": getattr(profile, binding[i], None) if binding[i] != "investable_cash" else investable_pct,
                    "room": round(weights[i], 4), "issuer": issuer,
                })
                failed.append(i)
                continue
            amount_base = profile.capital * weights[i] / 100.0
            per_share_base = company.price * normalized_fx[company.currency.upper()]
            if per_share_base <= 0:
                reject(company.identity(), "invalid_price", "invalid converted share price")
                failed.append(i)
                continue
            # US "Round Lot Size" (100/40/10) is a market-structure term, not a
            # minimum order: US stocks trade in single shares.
            lot_size = 1 if company.country.upper() == "US" else max(1, int(company.lot_size or 1))
            quantity = (floor(amount_base / per_share_base) // lot_size) * lot_size
            if quantity <= 0:
                reject(company.identity(), "minimum_lot", f"allocation {amount_base:.2f} {profile.base_currency.upper()} cannot buy one minimum lot ({lot_size} x {per_share_base:.2f})", amount=round(amount_base, 2), lot_size=lot_size, per_share_base=round(per_share_base, 4))
                failed.append(i)
                continue
            placed.append((entry, weights[i], quantity, binding[i]))
        if not failed:
            break
        # A slot freed by a candidate that cannot be sized is filled by the next
        # qualified, better-than-nothing candidate - never left empty while a
        # qualified name is reported as "cut".
        survivors = [entry for i, entry in enumerate(active) if i not in failed]
        while waiting and len(survivors) < max_positions:
            survivors.append(waiting.pop(0))
        if len(survivors) == len(active) and all(a is b for a, b in zip(survivors, active)):
            break
        active = survivors
    for entry in waiting:
        company = entry[0].company
        reject(company.identity(), "max_positions", f"qualified but ranked below the {max_positions} positions that could be allocated",
               max_positions=max_positions)

    allocations: list[PortfolioAllocation] = []
    allocated_pct = 0.0
    binding_counts: defaultdict[str, int] = defaultdict(int)
    for (candidate, score, confidence, issuer), weight, quantity, bound in placed:
        company = candidate.company
        fx_rate = normalized_fx[company.currency.upper()]
        lot_size = 1 if company.country.upper() == "US" else max(1, int(company.lot_size or 1))
        allocations.append(PortfolioAllocation(
            identity=company.identity(),
            ticker=company.ticker,
            country=company.country,
            exchange=company.exchange,
            currency=company.currency,
            weight_pct=round(weight, 4),
            amount_base_currency=round(profile.capital * weight / 100.0, 2),
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
        ))
        allocated_pct += weight
        binding_counts[bound] += 1

    if not allocations:
        return PortfolioProposal(
            status="NO_RECOMMENDATION",
            generated_at=utc_now_iso(),
            invested_pct=0.0,
            cash_pct=100.0,
            allocations=(),
            excluded=tuple(excluded),
            rejections=tuple(rejections),
            reasoning="eligible candidates could not be allocated within portfolio/lot constraints",
        )

    reasoning = "paper proposal only; no broker order was submitted"
    idle = investable_pct - allocated_pct
    if idle > 0.5:
        for rejection in rejections:
            if rejection["constraint"] in {"max_position_pct", "max_country_pct", "max_sector_pct"}:
                binding_counts[rejection["constraint"]] += 1
        binding_counts.pop("investable_cash", None)
        limits = ", ".join(f"{name} x{count}" for name, count in sorted(binding_counts.items(), key=lambda kv: -kv[1]))
        reasoning += (
            f"; {idle:.1f}% of the investable budget ({investable_pct:.1f}%) stays in cash because every "
            f"qualified candidate that could be placed is at a limit ({limits or "lot size"}) - the caps are not relaxed"
        )

    allocated_pct = min(100.0, allocated_pct)
    return PortfolioProposal(
        status="PAPER_PROPOSAL",
        generated_at=utc_now_iso(),
        invested_pct=round(allocated_pct, 4),
        cash_pct=round(100.0 - allocated_pct, 4),
        allocations=tuple(allocations),
        excluded=tuple(excluded),
        rejections=tuple(rejections),
        reasoning=reasoning,
    )
