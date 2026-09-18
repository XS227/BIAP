"""Profile-independent decision support metrics plus investor-fit helpers.

The stock assessment stays objective: the same company receives the same base
Kiasha score regardless of who is viewing it. Investor preferences are applied
only in portfolio construction so a strong stock can still be a poor fit for a
specific risk/liquidity objective.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .models import AgentSignal, EvidenceAssessment, GlobalCompany, InvestorProfile


def _safe_ratio(numerator: Optional[float], denominator: Optional[float], *, pct: bool = False) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    value = float(numerator) / float(denominator)
    return value * 100.0 if pct else value


def _signal_map(signals: Iterable[AgentSignal]) -> dict[str, AgentSignal]:
    return {signal.agent: signal for signal in signals}


def _band(value: Optional[float], *, low: float, high: float, labels: tuple[str, str, str]) -> str:
    if value is None:
        return "INSUFFICIENT_DATA"
    if value < low:
        return labels[0]
    if value < high:
        return labels[1]
    return labels[2]


def _outlook(weighted_votes: list[tuple[float, float]], evidence: EvidenceAssessment) -> str:
    if evidence.status == "BLOCK":
        return "DATA_BLOCKED"
    usable = [(vote, confidence) for vote, confidence in weighted_votes if confidence > 0]
    if not usable:
        return "INSUFFICIENT_DATA"
    weight = sum(confidence for _, confidence in usable)
    score = sum(vote * confidence for vote, confidence in usable) / weight if weight else 0.0
    if score >= 0.22:
        return "FAVORABLE"
    if score <= -0.22:
        return "CAUTION"
    return "MIXED"


def build_decision_table(
    company: GlobalCompany,
    signals: Iterable[AgentSignal],
    evidence: EvidenceAssessment,
    *,
    call: str,
    score: float,
    confidence: float,
) -> dict:
    """Return stable, explainable metrics commonly used in stock decisions."""

    signal_by_name = _signal_map(signals)
    forecast = signal_by_name.get("forecast")
    risk = signal_by_name.get("risk")
    liquidity = signal_by_name.get("liquidity")
    fundamental = signal_by_name.get("fundamental")
    quality = signal_by_name.get("quality")
    comparison = signal_by_name.get("comparison")

    range_position_pct = None
    if (
        company.price is not None
        and company.price_52w_low is not None
        and company.price_52w_high is not None
        and company.price_52w_high > company.price_52w_low
    ):
        range_position_pct = max(
            0.0,
            min(100.0, (company.price - company.price_52w_low) / (company.price_52w_high - company.price_52w_low) * 100.0),
        )

    volume_ratio = _safe_ratio(company.volume_today, company.avg_volume_30d)
    pe_vs_sector_pct = None
    if company.pe is not None and company.pe > 0 and company.sector_pe is not None and company.sector_pe > 0:
        pe_vs_sector_pct = (company.pe / company.sector_pe - 1.0) * 100.0

    debt_to_equity = _safe_ratio(company.total_debt, company.total_equity)
    current_ratio = _safe_ratio(company.current_assets, company.current_liabilities)
    roe_pct = _safe_ratio(company.net_income, company.total_equity, pct=True)
    roa_pct = _safe_ratio(company.net_income, company.total_assets, pct=True)

    momentum_values = [
        value for value in (company.return_1m_pct, company.return_3m_pct, company.return_6m_pct)
        if value is not None
    ]
    momentum = "INSUFFICIENT_DATA"
    if momentum_values:
        positives = sum(value > 0 for value in momentum_values)
        negatives = sum(value < 0 for value in momentum_values)
        average = sum(momentum_values) / len(momentum_values)
        if positives == len(momentum_values) or (positives >= 2 and average >= 4):
            momentum = "POSITIVE"
        elif negatives == len(momentum_values) or (negatives >= 2 and average <= -4):
            momentum = "NEGATIVE"
        else:
            momentum = "MIXED"

    valuation = "INSUFFICIENT_DATA"
    if pe_vs_sector_pct is not None:
        if pe_vs_sector_pct <= -15:
            valuation = "DISCOUNT_TO_SECTOR"
        elif pe_vs_sector_pct >= 15:
            valuation = "PREMIUM_TO_SECTOR"
        else:
            valuation = "NEAR_SECTOR"

    dividend = company.dividend_yield_pct
    if dividend is None:
        income = "INSUFFICIENT_DATA"
    elif dividend >= 4:
        income = "HIGH_YIELD"
    elif dividend >= 2:
        income = "MODERATE_YIELD"
    elif dividend > 0:
        income = "LOW_YIELD"
    else:
        income = "NO_CURRENT_YIELD"

    short_term = _outlook(
        [
            (forecast.vote, forecast.confidence) if forecast else (0.0, 0.0),
            (risk.vote, risk.confidence) if risk else (0.0, 0.0),
            (liquidity.vote, liquidity.confidence) if liquidity else (0.0, 0.0),
        ],
        evidence,
    )
    long_term = _outlook(
        [
            (fundamental.vote, fundamental.confidence) if fundamental else (0.0, 0.0),
            (quality.vote, quality.confidence) if quality else (0.0, 0.0),
            (comparison.vote, comparison.confidence) if comparison else (0.0, 0.0),
            (risk.vote, risk.confidence) if risk else (0.0, 0.0),
        ],
        evidence,
    )

    volatility_level = _band(
        company.volatility_annualized_pct,
        low=25.0,
        high=45.0,
        labels=("LOW", "MODERATE", "HIGH"),
    )
    drawdown_level = _band(
        abs(company.max_drawdown_pct) if company.max_drawdown_pct is not None else None,
        low=20.0,
        high=35.0,
        labels=("LOW", "ELEVATED", "HIGH"),
    )

    holder_action = {
        "BUY_CANDIDATE": "HOLD_OR_ADD_REVIEW",
        "HOLD_OR_WATCH": "HOLD_AND_MONITOR",
        "AVOID_OR_REVIEW": "REDUCE_OR_SELL_REVIEW",
        "NO_RECOMMENDATION": "NO_ACTION_DATA_INSUFFICIENT",
    }.get(call, "REVIEW")

    return {
        "shortTermOutlook": short_term,
        "longTermOutlook": long_term,
        "momentum": momentum,
        "riskLevel": volatility_level,
        "drawdownRisk": drawdown_level,
        "valuationView": valuation,
        "incomeProfile": income,
        "metrics": {
            "price": company.price,
            "position52wPct": range_position_pct,
            "return1mPct": company.return_1m_pct,
            "return3mPct": company.return_3m_pct,
            "return6mPct": company.return_6m_pct,
            "volatilityAnnualizedPct": company.volatility_annualized_pct,
            "maxDrawdownPct": company.max_drawdown_pct,
            "beta": company.beta,
            "volumeVs30d": volume_ratio,
            "marketCap": company.market_cap,
            "pe": company.pe,
            "sectorPe": company.sector_pe,
            "peVsSectorPct": pe_vs_sector_pct,
            "pb": company.pb,
            "evEbitda": company.ev_ebitda,
            "dividendYieldPct": company.dividend_yield_pct,
            "eps": company.eps,
            "bookValuePerShare": company.book_value_per_share,
            "revenueYoyPct": company.revenue_yoy_pct,
            "netMarginPct": company.net_margin_pct,
            "freeCashFlow": company.free_cash_flow,
            "debtToEquity": debt_to_equity,
            "currentRatio": current_ratio,
            "roePct": roe_pct,
            "roaPct": roa_pct,
        },
        "kiasha": {
            "call": call,
            "newPositionAction": call,
            "existingHolderAction": holder_action,
            "score": round(float(score), 6),
            "confidence": round(float(confidence), 6),
            "evidence": evidence.status,
        },
        "notes": (
            "Base stock assessment is profile-independent. Investor preferences are applied separately "
            "when constructing a portfolio."
        ),
    }


def _horizon_years(value: str) -> Optional[float]:
    text = (value or "").strip().lower().replace(" ", "")
    try:
        if text.endswith("m"):
            return float(text[:-1]) / 12.0
        if text.endswith("y+"):
            return float(text[:-2])
        if text.endswith("y"):
            return float(text[:-1])
        return float(text)
    except (TypeError, ValueError):
        return None


def profile_assessment(profile: InvestorProfile) -> dict:
    """Summarize investor constraints without changing objective stock quality."""

    tolerance = profile.risk_tolerance.strip().lower()
    score = {"low": 0, "conservative": 0, "medium": 1, "moderate": 1, "high": 2, "aggressive": 2}.get(tolerance, 1)
    years = _horizon_years(profile.horizon)
    if years is not None:
        if years >= 5:
            score += 1
        elif years < 1:
            score -= 1

    comfort = profile.max_drawdown_comfort_pct
    if comfort is not None:
        if comfort <= 15:
            score -= 1
        elif comfort >= 35:
            score += 1

    liquidity = profile.liquidity_need.strip().lower()
    if liquidity == "high":
        score -= 1

    if score <= 0:
        label = "CONSERVATIVE"
    elif score >= 3:
        label = "AGGRESSIVE_GROWTH"
    else:
        label = "BALANCED"

    return {
        "label": label,
        "riskTolerance": profile.risk_tolerance,
        "horizon": profile.horizon,
        "objectives": list(profile.objectives),
        "liquidityNeed": profile.liquidity_need,
        "maxDrawdownComfortPct": profile.max_drawdown_comfort_pct,
        "capital": profile.capital,
        "baseCurrency": profile.base_currency,
        "notes": "Suitability profile affects portfolio fit, not the underlying Kiasha stock score.",
    }


def preference_adjustment(company: GlobalCompany, profile: InvestorProfile) -> float:
    """Small suitability adjustment applied only inside PortfolioAgent."""

    objectives = {item.strip().lower() for item in profile.objectives}
    adjustment = 0.0

    if "income" in objectives and company.dividend_yield_pct is not None:
        if company.dividend_yield_pct >= 4:
            adjustment += 0.12
        elif company.dividend_yield_pct >= 2:
            adjustment += 0.06
        elif company.dividend_yield_pct <= 0:
            adjustment -= 0.05

    if "growth" in objectives and company.revenue_yoy_pct is not None:
        if company.revenue_yoy_pct >= 12:
            adjustment += 0.10
        elif company.revenue_yoy_pct < 0:
            adjustment -= 0.10

    if "value" in objectives and company.pe and company.pe > 0 and company.sector_pe and company.sector_pe > 0:
        relative = company.pe / company.sector_pe - 1.0
        if relative <= -0.15:
            adjustment += 0.10
        elif relative >= 0.30:
            adjustment -= 0.08

    if "capital_preservation" in objectives:
        if company.volatility_annualized_pct is not None:
            if company.volatility_annualized_pct <= 25:
                adjustment += 0.05
            elif company.volatility_annualized_pct >= 40:
                adjustment -= 0.14
        if company.max_drawdown_pct is not None and abs(company.max_drawdown_pct) >= 30:
            adjustment -= 0.12

    years = _horizon_years(profile.horizon)
    if years is not None and years < 1:
        values = [value for value in (company.return_1m_pct, company.return_3m_pct) if value is not None]
        if values:
            avg = sum(values) / len(values)
            adjustment += 0.08 if avg >= 4 else -0.08 if avg <= -4 else 0.0

    if profile.max_drawdown_comfort_pct is not None and company.max_drawdown_pct is not None:
        excess = abs(company.max_drawdown_pct) - profile.max_drawdown_comfort_pct
        if excess > 0:
            adjustment -= min(0.20, excess / 100.0)

    if profile.liquidity_need.strip().lower() == "high":
        if (
            company.avg_volume_30d not in (None, 0)
            and company.price not in (None, 0)
            and company.market_cap not in (None, 0)
        ):
            turnover_pct = company.avg_volume_30d * company.price / company.market_cap * 100.0
            if turnover_pct >= 0.10:
                adjustment += 0.04
            elif turnover_pct < 0.02:
                adjustment -= 0.10

    return max(-0.40, min(0.25, adjustment))
