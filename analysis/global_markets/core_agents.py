"""Market-agnostic BIAP core agents for the Global normalized schema.

These retain the roles of the Iran agents (fundamental, risk, forecast and
comparison) without calling TSETMC/CODAL directly. Provider adapters are the
only layer allowed to know where the data came from.
"""

from __future__ import annotations

from .models import AgentSignal, GlobalCompany


def _bounded(value: float) -> float:
    return max(-1.0, min(1.0, value))


def fundamental_agent(company: GlobalCompany) -> AgentSignal:
    vote = 0.0
    reasons: list[str] = []
    signals = 0

    if company.revenue_yoy_pct is not None:
        signals += 1
        growth = company.revenue_yoy_pct
        if growth > 10:
            vote += 0.4
            reasons.append(f"revenue +{growth:.1f}% YoY")
        elif growth < 0:
            vote -= 0.3
            reasons.append(f"revenue {growth:.1f}% YoY")
        else:
            reasons.append(f"revenue +{growth:.1f}% YoY")

    if company.net_margin_pct is not None:
        signals += 1
        margin = company.net_margin_pct
        previous = company.net_margin_prev_pct
        if margin < 0:
            vote -= 0.4
            reasons.append(f"net margin negative ({margin:.1f}%)")
        if previous is not None:
            delta = margin - previous
            if delta > 0:
                vote += 0.2
                reasons.append(f"margin improving ({delta:+.1f}pp)")
            elif delta < 0:
                vote -= 0.2
                reasons.append(f"margin declining ({delta:+.1f}pp)")

    if company.operating_cash_flow is not None:
        signals += 1
        if company.operating_cash_flow < 0:
            vote -= 0.25
            reasons.append("negative operating cash flow")
        else:
            vote += 0.1
            reasons.append("positive operating cash flow")

    if company.audit_opinion:
        signals += 1
        if company.audit_opinion.lower() in {"unqualified", "clean"}:
            reasons.append("audit opinion clean/unqualified")
        else:
            vote -= 0.45
            reasons.append(f"audit opinion: {company.audit_opinion}")

    confidence = min(0.8, 0.25 + 0.13 * signals) if signals else 0.0
    return AgentSignal(
        agent="fundamental",
        vote=_bounded(vote),
        confidence=confidence,
        reasoning="; ".join(reasons) or "verified fundamental evidence unavailable",
    )


def risk_agent(company: GlobalCompany) -> AgentSignal:
    vote = 0.0
    reasons: list[str] = []
    signals = 0

    if company.max_drawdown_pct is not None:
        signals += 1
        drawdown = abs(company.max_drawdown_pct)
        if drawdown >= 40:
            vote -= 0.35
        elif drawdown >= 25:
            vote -= 0.2
        else:
            vote += 0.05
        reasons.append(f"max drawdown {company.max_drawdown_pct:.1f}%")

    if company.volatility_annualized_pct is not None:
        signals += 1
        volatility = company.volatility_annualized_pct
        if volatility >= 60:
            vote -= 0.35
        elif volatility >= 40:
            vote -= 0.2
        elif volatility < 25:
            vote += 0.1
        reasons.append(f"annualized volatility {volatility:.1f}%")

    if company.total_liabilities is not None and company.total_equity not in (None, 0):
        signals += 1
        leverage = company.total_liabilities / abs(company.total_equity)
        if leverage > 3:
            vote -= 0.3
        elif leverage > 2:
            vote -= 0.15
        reasons.append(f"liabilities/equity {leverage:.2f}x")

    if company.total_debt is not None and company.operating_cash_flow not in (None, 0):
        signals += 1
        debt_to_ocf = company.total_debt / abs(company.operating_cash_flow)
        if debt_to_ocf > 6:
            vote -= 0.25
        elif debt_to_ocf < 2:
            vote += 0.05
        reasons.append(f"debt/operating cash flow {debt_to_ocf:.2f}x")

    if company.audit_opinion and company.audit_opinion.lower() not in {"unqualified", "clean"}:
        signals += 1
        vote -= 0.35
        reasons.append(f"audit risk: {company.audit_opinion}")

    confidence = min(0.8, 0.3 + 0.1 * signals) if signals else 0.0
    return AgentSignal(
        agent="risk",
        vote=_bounded(vote),
        confidence=confidence,
        reasoning="; ".join(reasons) or "verified risk metrics unavailable",
    )


def forecast_agent(company: GlobalCompany) -> AgentSignal:
    vote = 0.0
    reasons: list[str] = []
    signals = 0

    if company.avg_volume_30d not in (None, 0) and company.volume_today is not None:
        signals += 1
        ratio = company.volume_today / company.avg_volume_30d
        if ratio >= 2:
            vote += 0.2
        reasons.append(f"volume {ratio:.1f}x 30d average")

    pairs = (
        (company.return_1m_pct, "1m"),
        (company.return_3m_pct, "3m"),
        (company.return_6m_pct, "6m"),
    )
    momentum_values = [(value, label) for value, label in pairs if value is not None]
    if momentum_values:
        signals += 1
        positives = sum(value > 0 for value, _ in momentum_values)
        negatives = sum(value < 0 for value, _ in momentum_values)
        if positives == len(momentum_values):
            vote += 0.3
        elif negatives == len(momentum_values):
            vote -= 0.3
        reasons.append(
            "returns " + ", ".join(f"{label}={value:+.1f}%" for value, label in momentum_values)
        )

    high = company.price_52w_high
    low = company.price_52w_low
    price = company.price
    if high is not None and low is not None and price is not None and high > low:
        signals += 1
        position = max(0.0, min(1.0, (price - low) / (high - low)))
        if position < 0.30:
            vote += 0.1
        elif position > 0.90:
            vote -= 0.1
        reasons.append(f"52w range position {position:.0%}")

    confidence = min(0.75, 0.3 + 0.13 * signals) if signals else 0.0
    return AgentSignal(
        agent="forecast",
        vote=_bounded(vote),
        confidence=confidence,
        reasoning="; ".join(reasons) or "verified market history unavailable",
    )


def comparison_agent(company: GlobalCompany) -> AgentSignal:
    pe = company.pe
    sector_pe = company.sector_pe
    if pe is None or pe <= 0:
        return AgentSignal("comparison", 0.0, 0.0, "valid positive P/E unavailable")
    if sector_pe is None or sector_pe <= 0:
        return AgentSignal("comparison", 0.0, 0.25, f"P/E {pe:.2f}; peer/sector P/E unavailable")

    discount_pct = (sector_pe - pe) / sector_pe * 100.0
    vote = 0.0
    if discount_pct >= 30:
        vote = 0.6
    elif discount_pct >= 15:
        vote = 0.35
    elif discount_pct <= -30:
        vote = -0.5
    elif discount_pct <= -15:
        vote = -0.3

    relationship = "discount" if discount_pct >= 0 else "premium"
    return AgentSignal(
        agent="comparison",
        vote=vote,
        confidence=0.65,
        reasoning=f"P/E {pe:.2f} vs peer/sector {sector_pe:.2f} ({abs(discount_pct):.0f}% {relationship})",
    )


def run_core_agents(company: GlobalCompany) -> tuple[AgentSignal, ...]:
    return (
        fundamental_agent(company),
        risk_agent(company),
        forecast_agent(company),
        comparison_agent(company),
    )
