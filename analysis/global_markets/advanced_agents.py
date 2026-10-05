"""Additional low-noise BIAP Global agents.

These agents intentionally rely only on normalized, provider-verified fields that
already exist in GlobalCompany. Missing inputs reduce confidence rather than
triggering guessed values.
"""

from __future__ import annotations

from .models import AgentSignal, GlobalCompany


def _bounded(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _is_financial(company: GlobalCompany) -> bool:
    text = " ".join(filter(None, (company.sector, company.industry))).lower()
    tokens = (
        "bank", "banking", "insurance", "financial", "capital markets",
        "broker", "asset management", "credit services", "mortgage",
    )
    return any(token in text for token in tokens)


def quality_agent(company: GlobalCompany) -> AgentSignal:
    """Assess earnings/cash-flow quality without duplicating valuation logic."""

    vote = 0.0
    reasons: list[str] = []
    signals = 0
    financial = _is_financial(company)

    if company.net_margin_pct is not None:
        signals += 1
        margin = company.net_margin_pct
        if margin >= 15:
            vote += 0.20
        elif margin < 0:
            vote -= 0.30
        reasons.append(f"net margin {margin:.1f}%")

    if company.net_income is not None and company.net_income > 0 and company.operating_cash_flow is not None and not financial:
        signals += 1
        cash_conversion = company.operating_cash_flow / company.net_income
        if cash_conversion >= 1.0:
            vote += 0.30
        elif cash_conversion < 0.60:
            vote -= 0.30
        reasons.append(f"operating cash/net income {cash_conversion:.2f}x")

    if company.net_income is not None and company.net_income > 0 and company.free_cash_flow is not None and not financial:
        signals += 1
        fcf_conversion = company.free_cash_flow / company.net_income
        if fcf_conversion >= 0.80:
            vote += 0.20
        elif fcf_conversion < 0:
            vote -= 0.30
        reasons.append(f"free cash/net income {fcf_conversion:.2f}x")

    if company.total_assets not in (None, 0) and company.net_income is not None:
        signals += 1
        roa = company.net_income / abs(company.total_assets) * 100.0
        if roa >= 8:
            vote += 0.15
        elif roa < 1 and company.net_income >= 0:
            vote -= 0.10
        reasons.append(f"ROA {roa:.1f}%")

    if not financial and company.cash_and_equivalents is not None and company.total_debt is not None:
        signals += 1
        if company.cash_and_equivalents >= company.total_debt:
            vote += 0.15
            reasons.append("cash covers total debt")
        elif company.cash_and_equivalents > 0 and company.total_debt > company.cash_and_equivalents * 4:
            vote -= 0.15
            reasons.append("debt exceeds cash by >4x")
        else:
            reasons.append("cash/debt balance moderate")

    if company.restatement_flag is True:
        signals += 1
        vote -= 0.30
        reasons.append("restatement flag weakens earnings quality")

    if financial and any(value is not None for value in (company.operating_cash_flow, company.free_cash_flow, company.total_debt)):
        reasons.append("generic cash-conversion/debt heuristics suppressed for financial-sector issuer")

    confidence = min(0.82, 0.24 + 0.10 * signals) if signals else 0.0
    return AgentSignal(
        agent="quality",
        vote=_bounded(vote),
        confidence=confidence,
        reasoning="; ".join(reasons) or "verified quality metrics unavailable",
    )


def liquidity_agent(company: GlobalCompany) -> AgentSignal:
    """Assess tradability using scale-independent turnover and lot-size ratios."""

    vote = 0.0
    reasons: list[str] = []
    signals = 0

    if (
        company.avg_volume_30d not in (None, 0)
        and company.price not in (None, 0)
        and company.market_cap not in (None, 0)
    ):
        signals += 1
        turnover_pct = company.avg_volume_30d * company.price / company.market_cap * 100.0
        if turnover_pct >= 0.20:
            vote += 0.30
        elif turnover_pct >= 0.05:
            vote += 0.12
        elif turnover_pct < 0.01:
            vote -= 0.35
        reasons.append(f"30d average turnover {turnover_pct:.3f}% of market cap/day")

    if company.avg_volume_30d not in (None, 0) and company.lot_size not in (None, 0):
        signals += 1
        lot_share = company.lot_size / company.avg_volume_30d * 100.0
        if lot_share <= 0.10:
            vote += 0.12
        elif lot_share >= 5.0:
            vote -= 0.30
        reasons.append(f"minimum lot {lot_share:.3f}% of 30d average volume")

    if company.avg_volume_30d not in (None, 0) and company.volume_today is not None:
        signals += 1
        activity = company.volume_today / company.avg_volume_30d
        if activity < 0.15:
            vote -= 0.10
        reasons.append(f"today volume {activity:.2f}x 30d average")

    if company.price is None or company.price <= 0:
        vote = min(vote, 0.0)
        reasons.append("verified price unavailable")

    confidence = min(0.76, 0.26 + 0.14 * signals) if signals else 0.0
    return AgentSignal(
        agent="liquidity",
        vote=_bounded(vote),
        confidence=confidence,
        reasoning="; ".join(reasons) or "verified liquidity metrics unavailable",
    )


def run_advanced_agents(company: GlobalCompany) -> tuple[AgentSignal, ...]:
    return quality_agent(company), liquidity_agent(company)
