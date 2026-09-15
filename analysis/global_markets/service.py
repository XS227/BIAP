"""Country-aware orchestration for BIAP Global.

This service is the boundary between UI/API requests and provider/agent logic.
It validates country/exchange identity, enriches evidence with fault isolation,
runs the six-agent pipeline, and refuses to force a directional call when
verification/confidence is insufficient.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, Optional

from .agents import PortfolioCandidate, evidence_agent, portfolio_agent
from .core_agents import run_core_agents
from .country_packs import get_exchange
from .models import GlobalCompany, InvestorProfile
from .providers import ProviderDiagnostics, ProviderRegistry
from .runtime import build_registry


def instrument_seed(
    *,
    country: str,
    exchange: str,
    ticker: str,
    name: Optional[str] = None,
    currency: Optional[str] = None,
    isin: Optional[str] = None,
) -> GlobalCompany:
    spec = get_exchange(country, exchange)
    quote_currency = (currency or (spec.currencies[0] if spec.currencies else "")).strip().upper()
    if not quote_currency:
        raise ValueError(f"currency is required for {country}/{exchange}")
    ticker = ticker.strip()
    if not ticker:
        raise ValueError("ticker is required")
    return GlobalCompany(
        country=country.strip().upper(),
        exchange=spec.code,
        mic_code=spec.mic,
        currency=quote_currency,
        ticker=ticker,
        name=(name or ticker).strip(),
        isin=isin.strip().upper() if isin else None,
    )


def _weighted_score(signals) -> tuple[float, float]:
    weighted = 0.0
    confidence_total = 0.0
    for signal in signals:
        confidence = max(0.0, min(1.0, float(signal.confidence)))
        weighted += max(-1.0, min(1.0, float(signal.vote))) * confidence
        confidence_total += confidence
    if confidence_total <= 0:
        return 0.0, 0.0
    return weighted / confidence_total, confidence_total / max(1, len(signals))


def _evaluate(company: GlobalCompany, registry: ProviderRegistry):
    enriched, diagnostics = registry.enrich_best_effort(company)
    signals = run_core_agents(enriched)
    evidence = evidence_agent(enriched, signals)
    raw_score, mean_confidence = _weighted_score(signals)
    final_score = raw_score * evidence.confidence_multiplier
    final_confidence = mean_confidence * evidence.confidence_multiplier
    return enriched, diagnostics, signals, evidence, final_score, final_confidence


def _call(score: float, confidence: float, blocked: bool) -> str:
    if blocked or confidence < 0.35:
        return "NO_RECOMMENDATION"
    if score >= 0.25 and confidence >= 0.45:
        return "BUY_CANDIDATE"
    if score <= -0.25 and confidence >= 0.45:
        return "AVOID_OR_REVIEW"
    return "HOLD_OR_WATCH"


def _analysis_payload(enriched, diagnostics: ProviderDiagnostics, signals, evidence, score, confidence) -> dict:
    return {
        "identity": enriched.identity(),
        "country": enriched.country,
        "exchange": enriched.exchange,
        "mic": enriched.mic_code,
        "ticker": enriched.ticker,
        "name": enriched.name,
        "currency": enriched.currency,
        "call": _call(score, confidence, evidence.blocked),
        "score": round(score, 6),
        "confidence": round(confidence, 6),
        "providerDiagnostics": diagnostics.to_dict(),
        "evidence": asdict(evidence),
        "signals": [asdict(signal) for signal in signals],
        "company": asdict(enriched),
    }


def analyze_company(
    company: GlobalCompany,
    *,
    registry: Optional[ProviderRegistry] = None,
) -> dict:
    registry = registry or build_registry()
    evaluated = _evaluate(company, registry)
    return _analysis_payload(*evaluated)


def portfolio_from_instruments(
    profile: InvestorProfile,
    instruments: Iterable[GlobalCompany],
    *,
    registry: Optional[ProviderRegistry] = None,
    fx_to_base: Optional[dict[str, float]] = None,
) -> dict:
    registry = registry or build_registry()
    candidates: list[PortfolioCandidate] = []
    analyses: list[dict] = []

    for company in instruments:
        enriched, diagnostics, signals, evidence, score, confidence = _evaluate(company, registry)
        analyses.append(_analysis_payload(enriched, diagnostics, signals, evidence, score, confidence))
        candidates.append(PortfolioCandidate(enriched, signals, evidence))

    proposal = portfolio_agent(profile, candidates, fx_to_base=fx_to_base)
    return {
        "proposal": asdict(proposal),
        "analyses": analyses,
    }
