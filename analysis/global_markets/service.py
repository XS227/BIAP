"""Country-aware orchestration for BIAP Global.

This service is the boundary between UI/API requests and provider/agent logic.
It validates country/exchange identity, enriches evidence with fault isolation,
runs six scoring agents plus Evidence/Verification and Portfolio agents, and
refuses to force a directional call when verification/confidence is insufficient.
"""

from __future__ import annotations

from dataclasses import asdict, replace
import os
from typing import Iterable, Optional

from .advanced_agents import run_advanced_agents
from .agents import PortfolioCandidate, evidence_agent, portfolio_agent
from .core_agents import run_core_agents
from .country_packs import get_exchange
from .decision_support import build_decision_table, profile_assessment
from .fx import TwelveDataFXProvider
from .models import GlobalCompany, InvestorProfile, SourceEvidence
from .providers import ProviderDiagnostics, ProviderRegistry
from .runtime import build_registry
from .source_catalog import SOURCE_PLANS
from .universe import _ordinary_equity_row


def instrument_seed(
    *,
    country: str,
    exchange: str,
    ticker: str,
    name: Optional[str] = None,
    currency: Optional[str] = None,
    isin: Optional[str] = None,
    lei: Optional[str] = None,
) -> GlobalCompany:
    spec = get_exchange(country, exchange)
    quote_currency = (currency or (spec.currencies[0] if spec.currencies else "")).strip().upper()
    if not quote_currency:
        raise ValueError(f"currency is required for {country}/{exchange}")
    ticker = ticker.strip()
    if not ticker:
        raise ValueError("ticker is required")
    normalized_lei = lei.strip().upper() if lei else None
    if normalized_lei and (len(normalized_lei) != 20 or not normalized_lei.isalnum()):
        raise ValueError("LEI must be a 20-character alphanumeric identifier")
    return GlobalCompany(
        country=country.strip().upper(),
        exchange=spec.code,
        mic_code=spec.mic,
        currency=quote_currency,
        ticker=ticker,
        name=(name or ticker).strip(),
        isin=isin.strip().upper() if isin else None,
        lei=normalized_lei,
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


def _supported_operating_equity(company: GlobalCompany) -> bool:
    try:
        spec = get_exchange(company.country, company.exchange)
    except Exception:
        return False
    row = {
        "name": company.name,
        "type": company.instrument_type or "Common Stock",
        "cfi_code": company.raw_provider_fields.get("cfi"),
    }
    return _ordinary_equity_row(
        country=company.country,
        spec=spec,
        row=row,
        symbol=company.ticker,
        currency=company.currency,
    )


def _derive_metrics(company: GlobalCompany) -> GlobalCompany:
    """Fill mathematically derivable valuation fields without inventing inputs.

    Cross-currency listings are intentionally excluded from per-share valuation
    derivations because filing EPS/book value and quote price may not share the
    same currency or share class.
    """
    market_cap = company.market_cap
    book_value_per_share = company.book_value_per_share
    pe = company.pe
    pb = company.pb
    ev_ebitda = company.ev_ebitda

    same_currency = (
        not company.reporting_currency
        or company.reporting_currency.upper() == company.currency.upper()
    )
    shares = company.shares_outstanding
    price = company.price

    derived: list[str] = []
    if market_cap is None and price not in (None, 0) and shares not in (None, 0):
        market_cap = float(price) * float(shares)
        derived.append("market_cap=price*shares_outstanding")

    if same_currency and shares not in (None, 0) and company.total_equity is not None and book_value_per_share is None:
        book_value_per_share = float(company.total_equity) / float(shares)
        derived.append("book_value_per_share=equity/shares_outstanding")

    if same_currency and price not in (None, 0) and company.eps not in (None, 0) and float(company.eps) > 0 and pe is None:
        pe = float(price) / float(company.eps)
        derived.append("pe=price/eps")

    if same_currency and price not in (None, 0) and book_value_per_share not in (None, 0) and float(book_value_per_share) > 0 and pb is None:
        pb = float(price) / float(book_value_per_share)
        derived.append("pb=price/book_value_per_share")

    if (
        same_currency
        and ev_ebitda is None
        and market_cap is not None
        and company.ebitda not in (None, 0)
        and float(company.ebitda) > 0
    ):
        enterprise_value = float(market_cap)
        if company.total_debt is not None:
            enterprise_value += float(company.total_debt)
        if company.cash_and_equivalents is not None:
            enterprise_value -= float(company.cash_and_equivalents)
        if enterprise_value > 0:
            ev_ebitda = enterprise_value / float(company.ebitda)
            derived.append("ev_ebitda=(market_cap+debt-cash)/ebitda")

    if not derived:
        return company

    return replace(
        company,
        market_cap=market_cap,
        book_value_per_share=book_value_per_share,
        pe=pe,
        pb=pb,
        ev_ebitda=ev_ebitda,
        raw_provider_fields={
            **company.raw_provider_fields,
            "derived_metrics": derived,
        },
        sources=[
            *company.sources,
            SourceEvidence(
                provider="biap-derived-metrics",
                source_type="derived_valuation_metric",
                quality=0.9,
                notes="; ".join(derived),
            ),
        ],
    )


def _evaluate(company: GlobalCompany, registry: ProviderRegistry):
    if not _supported_operating_equity(company):
        raise ValueError(
            f"{company.ticker} is not a supported ordinary operating-company equity; "
            "leveraged/inverse products, units, warrants, SPAC shells and structured securities are excluded"
        )
    enriched, diagnostics = registry.enrich_best_effort(company)
    enriched = _derive_metrics(enriched)
    signals = run_core_agents(enriched) + run_advanced_agents(enriched)
    evidence = evidence_agent(enriched, signals)
    raw_score, mean_confidence = _weighted_score(signals)
    final_score = raw_score * evidence.confidence_multiplier
    final_confidence = mean_confidence * evidence.confidence_multiplier
    return enriched, diagnostics, signals, evidence, final_score, final_confidence


def _call(score: float, confidence: float, evidence_status: str) -> str:
    # New BUY candidates are held to the strictest evidence state. WARN can
    # still show analysis, but cannot be promoted into a fresh buy idea.
    if evidence_status == "BLOCK" or confidence < 0.35:
        return "NO_RECOMMENDATION"
    if score >= 0.25 and confidence >= 0.45 and evidence_status == "PASS":
        return "BUY_CANDIDATE"
    if score <= -0.25 and confidence >= 0.45:
        return "AVOID_OR_REVIEW"
    return "HOLD_OR_WATCH"


def _source_plan_payload(country: str) -> dict:
    code = country.strip().upper()
    plan = dict(SOURCE_PLANS.get(code, {}))
    status = str(plan.get("status") or "")
    configured = status not in {"market-ready", ""}
    runtime_note = None
    if code == "JP":
        configured = bool((os.environ.get("BIAP_EDINET_API_KEY") or "").strip())
        if not configured:
            runtime_note = "EDINET adapter exists but BIAP_EDINET_API_KEY is not configured on the server."
    elif code == "KR":
        configured = bool((os.environ.get("BIAP_OPENDART_API_KEY") or "").strip())
        if not configured:
            runtime_note = "OpenDART adapter exists but BIAP_OPENDART_API_KEY is not configured on the server."
    elif status == "partial":
        runtime_note = (
            "A verified official fundamentals adapter is connected for a strict issuer allow-list; "
            "unsupported tickers remain blocked until an official source is added."
        )
    elif status == "market-ready":
        runtime_note = "Market routing is available; verified official fundamentals adapter is not connected yet."
    plan["runtimeConfigured"] = configured
    if runtime_note:
        plan["runtimeNote"] = runtime_note
    return plan


def _analysis_payload(enriched, diagnostics: ProviderDiagnostics, signals, evidence, score, confidence) -> dict:
    call = _call(score, confidence, evidence.status)
    return {
        "identity": enriched.identity(),
        "country": enriched.country,
        "exchange": enriched.exchange,
        "mic": enriched.mic_code,
        "ticker": enriched.ticker,
        "name": enriched.name,
        "isin": enriched.isin,
        "lei": enriched.lei,
        "currency": enriched.currency,
        "call": call,
        "score": round(score, 6),
        "confidence": round(confidence, 6),
        "providerDiagnostics": diagnostics.to_dict(),
        "sourcePlan": _source_plan_payload(enriched.country),
        "evidence": asdict(evidence),
        "signals": [asdict(signal) for signal in signals],
        "decisionTable": build_decision_table(
            enriched,
            signals,
            evidence,
            call=call,
            score=score,
            confidence=confidence,
        ),
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
    staged = [_evaluate(company, registry) for company in instruments]

    base = profile.base_currency.strip().upper()
    rates = {
        currency.strip().upper(): float(rate)
        for currency, rate in (fx_to_base or {}).items()
        if float(rate) > 0
    }
    rates[base] = 1.0
    required_currencies = {enriched.currency.upper() for enriched, *_ in staged}
    missing_fx = sorted(currency for currency in required_currencies if currency not in rates)
    fx_errors: dict[str, str] = {}

    if missing_fx and os.environ.get("BIAP_GLOBAL_MARKET_API_KEY"):
        fx_provider = TwelveDataFXProvider()
        for currency in missing_fx:
            try:
                rates[currency] = fx_provider.rate(currency, base)
            except Exception as exc:
                fx_errors[currency] = str(exc)[:240]

    candidates: list[PortfolioCandidate] = []
    analyses: list[dict] = []
    for enriched, diagnostics, signals, evidence, score, confidence in staged:
        currency = enriched.currency.upper()
        block_reasons: list[str] = []
        if evidence.status != "PASS":
            block_reasons.append(f"portfolio requires PASS evidence, got {evidence.status}")
        if currency not in rates:
            block_reasons.append(f"verified FX rate {currency}/{base} unavailable")

        portfolio_evidence = evidence
        if block_reasons:
            missing = list(evidence.missing_critical)
            if currency not in rates:
                missing.append("fx_rate")
            portfolio_evidence = replace(
                evidence,
                status="BLOCK",
                confidence_multiplier=0.0,
                missing_critical=tuple(dict.fromkeys(missing)),
                reasoning=f"{evidence.reasoning}; " + "; ".join(block_reasons),
            )

        payload = _analysis_payload(enriched, diagnostics, signals, evidence, score, confidence)
        payload["portfolioEligible"] = portfolio_evidence.status == "PASS"
        if currency in fx_errors:
            payload["fxError"] = fx_errors[currency]
        analyses.append(payload)
        candidates.append(PortfolioCandidate(enriched, signals, portfolio_evidence))

    proposal = portfolio_agent(profile, candidates, fx_to_base=rates)
    return {
        "proposal": asdict(proposal),
        "profileAssessment": profile_assessment(profile),
        "fxToBase": rates,
        "fxErrors": fx_errors,
        "analyses": analyses,
    }
