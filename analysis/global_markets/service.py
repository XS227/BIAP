"""Country-aware orchestration for BIAP Global.

This service is the boundary between UI/API requests and provider/agent logic.
It validates country/exchange identity, enriches evidence with fault isolation,
runs six scoring agents plus Evidence/Verification, independent distress/credit
assessment and Portfolio agents, and refuses to force a directional call when
verification/confidence is insufficient.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import os
import re
from statistics import median
from typing import Iterable, Optional

from .advanced_agents import run_advanced_agents
from .agents import PortfolioCandidate, evidence_agent, portfolio_agent
from .evidence_contract import fundamental_evidence_contract
from .core_agents import run_core_agents
from .country_packs import get_exchange
from .credit_scoring import score_legal_entity_company
from .decision_support import build_decision_table, profile_assessment
from .distress import distress_agent
from .governance import decision_governance_agent
from .opportunity import classify_opportunity
from .exchange_shares import apply_to_company as apply_exchange_share_counts
from .fx import ECBReferenceFXProvider, TwelveDataFXProvider
from .issuer import issuer_key_of
from .sector_reference import apply_sector_reference
from .models import DistressAssessment, GlobalCompany, InvestorProfile, SourceEvidence
from .providers import ProviderDiagnostics, ProviderRegistry
from .runtime import build_registry
from .source_cache import data_root, read_json
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


def _peer_pe_benchmark(company: GlobalCompany) -> tuple[Optional[float], Optional[str], int]:
    """Return a recent derived peer P/E benchmark from the persisted market scan.

    This is deliberately a comparison metric, never official filing evidence.
    Same-sector peers are preferred when at least three valid peers exist;
    otherwise a broader same-exchange median requires at least five peers.
    """
    country = "".join(ch for ch in company.country.upper() if ch.isalnum() or ch in {"-", "_"})
    exchange = "".join(ch for ch in company.exchange.upper() if ch.isalnum() or ch in {"-", "_"})
    wrapper = read_json(data_root() / "scan-cache" / country / f"{exchange}.json", default=None)
    if not isinstance(wrapper, dict) or wrapper.get("schemaVersion") not in {1, 2, 3}:
        return None, None, 0

    try:
        cached_at = datetime.fromisoformat(str(wrapper.get("cachedAt") or "").replace("Z", "+00:00"))
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - cached_at.astimezone(timezone.utc)).total_seconds() / 3600.0
    except ValueError:
        return None, None, 0
    if age_hours < 0 or age_hours > 24:
        return None, None, 0

    payload = wrapper.get("payload")
    rows = payload.get("deepResults") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None, None, 0

    same_sector: list[float] = []
    same_market: list[float] = []
    target_sector = (company.sector or "").strip().casefold()
    for row in rows:
        if not isinstance(row, dict):
            continue
        peer = row.get("company")
        if not isinstance(peer, dict):
            continue
        if str(peer.get("ticker") or "").strip().upper() == company.ticker.strip().upper():
            continue
        # Another share class of the same issuer (GOOG vs GOOGL) is not a peer.
        if issuer_key_of(peer) == issuer_key_of(company):
            continue
        try:
            pe = float(peer.get("pe"))
        except (TypeError, ValueError):
            continue
        if not (0 < pe < 500):
            continue
        same_market.append(pe)
        peer_sector = str(peer.get("sector") or "").strip().casefold()
        if target_sector and peer_sector and peer_sector == target_sector:
            same_sector.append(pe)

    if len(same_sector) >= 3:
        return float(median(same_sector)), "same_sector_scan_median", len(same_sector)
    if len(same_market) >= 5:
        return float(median(same_market)), "same_exchange_scan_median", len(same_market)
    return None, None, 0


_CLASS_SUFFIX = re.compile(r"[.\-/ ](?:[A-Z]|[A-Z]{1,2}\d?|SDB|PREF|PR)$")


def _has_share_class_suffix(ticker: str) -> bool:
    return bool(_CLASS_SUFFIX.search((ticker or "").strip().upper()))


def _fx_context(company: GlobalCompany) -> dict:
    """Date-aligned reporting->listing FX for one company (see ``fx_history``).

    Returns ``{"ok": True, "from", "to", "balance", "flow"}`` or
    ``{"ok": False, "reason"}``. Never raises and never guesses a date.
    """
    from datetime import date, timedelta
    from . import fx_history

    reporting = str(company.reporting_currency or "").upper()
    listing = str(company.currency or "").upper()
    out = {"ok": False, "from": reporting, "to": listing}
    if not company.filing_period_end:
        return {**out, "reason": "filing_period_end_missing"}
    try:
        period_end = date.fromisoformat(str(company.filing_period_end)[:10])
    except ValueError:
        return {**out, "reason": "filing_period_end_unparseable"}
    provider = fx_history.default_provider()
    if not provider.available():
        return {**out, "reason": "fx_history_cache_unavailable"}
    try:
        balance = provider.rate(reporting, listing, period_end)
        start = period_end - timedelta(days=364)
        flow = provider.average(reporting, listing, start, period_end)
    except Exception as exc:  # GlobalProviderError and malformed-cache errors alike
        return {**out, "reason": f"{type(exc).__name__}:{str(exc)[:120]}"}
    return {**out, "ok": True, "balance": balance.as_dict(), "flow": flow.as_dict(),
            "method": "balance_items@period_end_spot;flows@fiscal_year_mean;price/market_cap in listing currency"}


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
    dividend_yield_pct = company.dividend_yield_pct
    sector_pe = company.sector_pe

    same_currency = (
        not company.reporting_currency
        or company.reporting_currency.upper() == company.currency.upper()
    )
    shares = company.shares_outstanding
    price = company.price

    derived: list[str] = []
    # Cross-currency reporters: each filing quantity is converted into the
    # listing currency at the ECB reference rate of its own date (balance sheet
    # instants at the period-end fixing, flows at the fiscal-year mean). Without
    # a verifiable rate the per-share ratios stay suppressed, as before.
    fx_info: dict = {}
    balance_rate = flow_rate = 1.0
    if not same_currency:
        fx_info = _fx_context(company)
        if fx_info.get("ok"):
            balance_rate = float(fx_info["balance"]["rate"])
            flow_rate = float(fx_info["flow"]["rate"])
            same_currency = True
            derived.append(
                f"fx_converted:{fx_info['from']}->{fx_info['to']}"
                f";balance_rate={balance_rate:.6g}@{fx_info['balance']['rate_date']}"
                f";flow_rate={flow_rate:.6g}(mean of {fx_info['flow']['observations']} fixings {fx_info['flow']['requested']})"
                f";source={fx_info['balance']['provider']}"
            )
        else:
            derived.append(f"fx_unavailable:{fx_info.get('reason', 'unknown')}")
    eps_reporting = company.eps
    eps = None if company.eps is None else float(company.eps) * flow_rate
    equity = None if company.total_equity is None else float(company.total_equity) * balance_rate
    debt = None if company.total_debt is None else float(company.total_debt) * balance_rate
    cash = None if company.cash_and_equivalents is None else float(company.cash_and_equivalents) * balance_rate
    ebitda = None if company.ebitda is None else float(company.ebitda) * flow_rate
    dps = None if company.dividend_per_share is None else float(company.dividend_per_share) * flow_rate
    if (
        eps not in (None, 0)
        and company.net_income not in (None, 0)
        and (float(eps) > 0) != (float(company.net_income) > 0)
    ):
        # Volvo Cars FY2025: the filing tags BasicEarningsLossPerShare = +0.06
        # while ProfitLoss = -2,968m. The filed figures contradict each other,
        # so neither a P/E derived from the EPS nor a provider-supplied P/E is
        # trustworthy. Withhold both (never flip the sign) and document it.
        derived.append(
            f"eps_withheld:sign_contradicts_net_income(eps={float(eps):.6g},net_income={float(company.net_income):.6g});pe_suppressed"
        )
        eps = None
        eps_reporting = None
        pe = None
    if same_currency and price not in (None, 0) and eps not in (None, 0):
        # A per-share fact mis-scaled by the filer (EPS 0.655 tagged in
        # thousands -> 655) reaches us from any source, including snapshots
        # cached before the iXBRL guard. Positive EPS above the price (P/E < 1)
        # or a loss per share above 20x the price is withheld, never rescaled.
        ratio = float(eps) / float(price)
        if ratio > 1.0 or ratio < -20.0:
            derived.append(f"eps_withheld:implausible_vs_price(eps={float(eps):.6g},price={float(price):.6g})")
            eps = None
            eps_reporting = None
    if (
        same_currency
        and shares not in (None, 0)
        and eps_reporting not in (None, 0)
        and float(eps_reporting) > 0
        and company.net_income not in (None, 0)
        and float(company.net_income) > 0
    ):
        # Nextpower (NXT): a 2023 share count (62m) next to FY2026 diluted
        # shares of ~152m (net income / EPS) understated market cap 2.5x. A
        # share count more than 2x away from net income / EPS is not used for
        # market cap, book value per share or EV/EBITDA; it is withheld.
        implied_shares = float(company.net_income) / float(eps_reporting)
        if not 0.5 <= float(shares) / implied_shares <= 2.0:
            derived.append(
                f"shares_withheld:inconsistent_with_net_income_over_eps(shares={float(shares):.6g},implied={implied_shares:.6g})"
            )
            shares = None
    exchange_cap = company.raw_provider_fields.get("exchange_market_cap")
    if (
        isinstance(exchange_cap, dict)
        and market_cap is not None
        and market_cap == exchange_cap.get("value")
        and price not in (None, 0)
        and eps_reporting not in (None, 0)
        and company.net_income not in (None, 0)
        and float(company.net_income) / float(eps_reporting) > 0
    ):
        # Exchange-reported market cap vs price * (net income / EPS): a gap of
        # more than 2x means another share class / a different issuer scope.
        implied_cap = float(price) * float(company.net_income) / float(eps_reporting)   # > 0 by the guard above
        if not 0.5 <= float(market_cap) / implied_cap <= 2.0:
            derived.append(
                f"market_cap_withheld:exchange_value_inconsistent_with_net_income_over_eps(cap={float(market_cap):.6g},implied={implied_cap:.6g})"
            )
            market_cap = None
    shares_basis = ""
    for meta_key in ("oam_credit_extraction", "esef_credit_extraction"):
        meta = company.raw_provider_fields.get(meta_key)
        if isinstance(meta, dict) and meta.get("shares_outstanding_basis"):
            shares_basis = str(meta["shares_outstanding_basis"])
    if (
        shares_basis
        and company.shares_outstanding is not None
        and shares is not None
        and _has_share_class_suffix(company.ticker)
    ):
        # An issued count is the company total across classes; a class-suffixed
        # ticker prices only one class, so price*issued would be wrong.
        derived.append("shares_withheld:issued_count_not_verified_single_class(class_suffixed_ticker)")
        shares = None
    if market_cap is None and price not in (None, 0) and shares not in (None, 0):
        market_cap = float(price) * float(shares)
        derived.append(
            "market_cap=price*shares_issued(labelled fallback: single-class filing, treasury shares not deducted)"
            if shares_basis and shares == company.shares_outstanding
            else "market_cap=price*shares_outstanding"
        )

    if same_currency and shares not in (None, 0) and equity is not None and book_value_per_share is None:
        book_value_per_share = float(equity) / float(shares)
        derived.append("book_value_per_share=equity/shares_outstanding")

    if same_currency and price not in (None, 0) and eps not in (None, 0) and float(eps) > 0 and pe is None:
        # EPS above the price was withheld above (CIR FY2025: EUR 0.0325
        # tagged in thousands -> P/E 0.02), so P/E is only derived from a
        # plausible per-share figure.
        pe = float(price) / float(eps)
        derived.append("pe=price/eps")

    if (
        same_currency
        and dividend_yield_pct is None
        and price not in (None, 0)
        and dps is not None
        and float(dps) >= 0
    ):
        dividend_yield_pct = float(dps) / float(price) * 100.0
        derived.append("dividend_yield_pct=annual_dividend_per_share/price")

    peer_scope = None
    peer_count = 0
    exchange_pe_median = None
    if sector_pe is None:
        peer_pe, peer_scope, peer_count = _peer_pe_benchmark(company)
        if peer_pe is not None and peer_scope == "same_sector_scan_median":
            sector_pe = peer_pe
            derived.append(f"sector_pe={peer_scope}")
        elif peer_pe is not None:
            # An exchange-wide median is not a sector benchmark: keep it as
            # context only so valuation agents never score against it.
            exchange_pe_median = peer_pe
            derived.append(f"exchange_pe_median={peer_scope}(informational, not used as sector_pe)")

    if same_currency and price not in (None, 0) and book_value_per_share not in (None, 0) and float(book_value_per_share) > 0 and pb is None:
        pb = float(price) / float(book_value_per_share)
        derived.append("pb=price/book_value_per_share")
    elif (
        same_currency
        and pb is None
        and market_cap not in (None, 0)
        and equity not in (None, 0)
        and float(equity) > 0
    ):
        # No verified share count, but an exchange-reported / derived market cap
        # exists: P/B = market cap / book equity is the same ratio.
        pb = float(market_cap) / float(equity)
        derived.append("pb=market_cap/total_equity")

    if (
        same_currency
        and ev_ebitda is None
        and market_cap is not None
        and ebitda not in (None, 0)
        and float(ebitda) > 0
    ):
        enterprise_value = float(market_cap)
        if debt is not None:
            enterprise_value += float(debt)
        if cash is not None:
            enterprise_value -= float(cash)
        if enterprise_value > 0:
            ev_ebitda = enterprise_value / float(ebitda)
            derived.append("ev_ebitda=(market_cap+debt-cash)/ebitda")

    if not derived:
        return company

    return replace(
        company,
        market_cap=market_cap,
        shares_outstanding=shares,
        book_value_per_share=book_value_per_share,
        eps=eps_reporting,
        pe=pe,
        sector_pe=sector_pe,
        pb=pb,
        ev_ebitda=ev_ebitda,
        dividend_yield_pct=dividend_yield_pct,
        raw_provider_fields={
            **company.raw_provider_fields,
            "derived_metrics": derived,
            **({
                "peer_pe_benchmark_scope": peer_scope,
                "peer_pe_benchmark_count": peer_count,
                # The cohort is the deep-analyzed sample of the daily scan,
                # not every listed company; exchange-wide medians are not
                # sector-specific and must not be read as a sector P/E.
                "peer_pe_benchmark_cohort": "deep_analyzed_scan_sample_excluding_same_issuer",
                "peer_pe_benchmark_is_sector_specific": peer_scope == "same_sector_scan_median",
                **({"exchange_pe_median_informational": exchange_pe_median} if exchange_pe_median is not None else {}),
            } if peer_scope else {}),
            **({"fx_conversion": fx_info} if fx_info else {}),
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
    enriched = apply_sector_reference(enriched)
    enriched = apply_exchange_share_counts(enriched)
    enriched = _derive_metrics(enriched)
    signals = run_core_agents(enriched) + run_advanced_agents(enriched)
    evidence = evidence_agent(enriched, signals)
    distress = distress_agent(enriched)
    credit_scoring = score_legal_entity_company(enriched, distress)
    raw_score, decision_confidence = _weighted_score(signals)
    final_score = raw_score * evidence.confidence_multiplier
    overall_confidence = decision_confidence * evidence.confidence_multiplier
    return (
        enriched,
        diagnostics,
        signals,
        evidence,
        distress,
        credit_scoring,
        raw_score,
        final_score,
        decision_confidence,
        overall_confidence,
    )


def _call(
    score: float,
    confidence: float,
    evidence_status: str,
    distress: Optional[DistressAssessment] = None,
) -> str:
    # New BUY candidates are held to the strictest evidence state. WARN can
    # still show analysis, but cannot be promoted into a fresh buy idea.
    if evidence_status == "BLOCK" or confidence < 0.35:
        return "NO_RECOMMENDATION"
    if score >= 0.25 and confidence >= 0.45 and evidence_status == "PASS":
        if distress is not None and distress.positive_block:
            return "NO_RECOMMENDATION"
        return "BUY_CANDIDATE"
    if score <= -0.25 and confidence >= 0.45:
        return "AVOID_OR_REVIEW"
    return "HOLD_OR_WATCH"


def _distress_consistency(preliminary_call: str, distress: DistressAssessment) -> str:
    if distress.status in {"HIGH_RISK", "ELEVATED_RISK"}:
        if preliminary_call == "BUY_CANDIDATE":
            return "MATERIAL_CONTRADICTION"
        if preliminary_call == "AVOID_OR_REVIEW":
            return "STRONG_CORROBORATION"
        return "RISK_CAUTION"
    if distress.status == "LOW_RISK":
        if preliminary_call == "BUY_CANDIDATE":
            return "SUPPORTIVE"
        if preliminary_call == "AVOID_OR_REVIEW":
            return "MIXED"
    if distress.status == "NOT_APPLICABLE":
        return "MODEL_NOT_APPLICABLE"
    return "INSUFFICIENT_DISTRESS_DATA"


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


def _analysis_payload(
    enriched,
    diagnostics: ProviderDiagnostics,
    signals,
    evidence,
    distress: DistressAssessment,
    credit_scoring: dict,
    raw_score: float,
    score: float,
    decision_confidence: float,
    confidence: float,
) -> dict:
    preliminary_call = _call(score, confidence, evidence.status)
    governance = decision_governance_agent(
        proposed_call=preliminary_call,
        score=score,
        overall_confidence=confidence,
        decision_confidence=decision_confidence,
        evidence=evidence,
        distress=distress,
    )
    call = governance.final_call
    distress_gate_applied = (
        preliminary_call == "BUY_CANDIDATE"
        and call == "NO_RECOMMENDATION"
        and distress.positive_block
    )
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
        "rawScore": round(raw_score, 6),
        # Backward-compatible "confidence" remains the overall calibrated value.
        "confidence": round(confidence, 6),
        "decisionConfidence": round(decision_confidence, 6),
        "evidenceConfidence": round(evidence.confidence_multiplier, 6),
        "overallCalibratedConfidence": round(confidence, 6),
        "providerDiagnostics": diagnostics.to_dict(),
        "sourcePlan": _source_plan_payload(enriched.country),
        "evidence": asdict(evidence),
        "fundamentalEvidence": fundamental_evidence_contract(enriched),
        "distress": asdict(distress),
        "creditScoring": credit_scoring,
        "governance": asdict(governance),
        "opportunity": classify_opportunity(
            preliminary_call=preliminary_call,
            final_call=call,
            score=score,
            confidence=confidence,
            evidence=asdict(evidence),
            distress=asdict(distress),
            governance=asdict(governance),
            signals=signals,
            metrics={"return6mPct": enriched.return_6m_pct},
        ),
        "decisionIntegrity": {
            "preliminaryCall": preliminary_call,
            "finalCall": call,
            "distressGateApplied": distress_gate_applied,
            "crossAgentConsistency": _distress_consistency(preliminary_call, distress),
            "governanceAction": governance.action,
            "governanceAccepted": governance.accepted,
            "governanceEscalated": governance.escalated,
            "governanceAbstained": governance.abstained,
            "notes": "Agent 8 governs whether the analysis may be accepted/reviewed/abstained. Agent 9 is an independent distress/credit sidecar. Agent 10 is report-only credit scoring for the selected legal entity and never creates or changes BUY/SELL decisions.",
        },
        "signals": [asdict(signal) for signal in signals],
        "decisionTable": build_decision_table(
            enriched,
            signals,
            evidence,
            call=call,
            score=score,
            confidence=confidence,
            decision_confidence=decision_confidence,
            distress=distress,
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


def resolve_fx_rates(currencies, base: str) -> tuple[dict[str, float], dict[str, str], dict[str, dict]]:
    """Rates (currency -> base) from explicit sources only; failures are reported, never defaulted."""
    rates: dict[str, float] = {}
    errors: dict[str, str] = {}
    sources: dict[str, dict] = {}
    currencies = list(currencies)
    if not currencies:
        return rates, errors, sources
    providers = []
    if os.environ.get("BIAP_GLOBAL_MARKET_API_KEY"):
        providers.append(TwelveDataFXProvider())
    providers.append(ECBReferenceFXProvider())
    for currency in currencies:
        failures: list[str] = []
        for provider in providers:
            try:
                rates[currency] = provider.rate(currency, base)
            except Exception as exc:
                failures.append(f"{provider.provider_id}: {str(exc)[:160]}")
                continue
            sources[currency] = provider.source_info() if hasattr(provider, "source_info") else {"provider": provider.provider_id}
            break
        else:
            errors[currency] = " | ".join(failures)[:300]
    return rates, errors, sources


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

    fx_sources: dict[str, dict] = {
        currency.strip().upper(): {"provider": "client-supplied"} for currency in (fx_to_base or {})
    }
    resolved, fx_errors, resolved_sources = resolve_fx_rates(missing_fx, base)
    rates.update(resolved)
    fx_sources.update(resolved_sources)

    candidates: list[PortfolioCandidate] = []
    analyses: list[dict] = []
    for (
        enriched,
        diagnostics,
        signals,
        evidence,
        distress,
        credit_scoring,
        raw_score,
        score,
        decision_confidence,
        confidence,
    ) in staged:
        currency = enriched.currency.upper()
        block_reasons: list[str] = []
        if evidence.status != "PASS":
            block_reasons.append(f"portfolio requires PASS evidence, got {evidence.status}")
        if distress.positive_block:
            block_reasons.append(f"distress safety gate: {distress.reasoning}")
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

        payload = _analysis_payload(
            enriched,
            diagnostics,
            signals,
            evidence,
            distress,
            credit_scoring,
            raw_score,
            score,
            decision_confidence,
            confidence,
        )
        payload["portfolioEligible"] = portfolio_evidence.status == "PASS"
        if currency in fx_errors:
            payload["fxError"] = fx_errors[currency]
        analyses.append(payload)
        candidates.append(PortfolioCandidate(enriched, signals, portfolio_evidence, distress))

    proposal = portfolio_agent(profile, candidates, fx_to_base=rates)
    return {
        "proposal": asdict(proposal),
        "profileAssessment": profile_assessment(profile),
        "fxToBase": rates,
        "fxSources": fx_sources,
        "fxErrors": fx_errors,
        "analyses": analyses,
    }
