"""
BIAP agents: fundamental analysis, risk, forecasting, comparison.

Each agent reads the normalized company record and returns a bounded vote plus
confidence and auditable reasoning. Missing data stays neutral instead of being
guessed.
"""

from dataclasses import dataclass

from company_builder import availability


@dataclass
class AgentVote:
    agent: str
    vote: float
    confidence: float
    reasoning: str


def fundamental_agent(company: dict) -> AgentVote:
    avail = availability(company)
    if not avail["codal"]:
        return AgentVote("fundamental", 0.0, 0.0, "no CODAL fundamentals connected yet")

    codal = company["codal"]
    revenue_yoy = codal.get("revenue_yoy_pct")
    net_margin = codal.get("net_margin_pct")
    net_margin_prev = codal.get("net_margin_prev_pct")
    audit_opinion = codal.get("audit_opinion")
    related_party_flags = codal.get("related_party_flags")

    vote = 0.0
    reasons = []
    quantitative_signals = 0

    if revenue_yoy is not None:
        quantitative_signals += 1
        if revenue_yoy > 10:
            vote += 0.4
            reasons.append(f"revenue +{revenue_yoy:.1f}% YoY")
        elif revenue_yoy < 0:
            vote -= 0.3
            reasons.append(f"revenue {revenue_yoy:.1f}% YoY")
        else:
            reasons.append(f"revenue +{revenue_yoy:.1f}% YoY")

    if net_margin is not None and net_margin_prev is not None:
        quantitative_signals += 1
        margin_delta = net_margin - net_margin_prev
        if margin_delta > 0:
            vote += 0.3
            reasons.append(f"margin improving ({margin_delta:+.1f}pp)")
        elif margin_delta < 0:
            vote -= 0.2
            reasons.append(f"margin declining ({margin_delta:+.1f}pp)")
        else:
            reasons.append("net margin unchanged")

    if audit_opinion is not None and audit_opinion != "unqualified":
        vote -= 0.5
        reasons.append(f"audit opinion: {audit_opinion}")

    if related_party_flags is not None and related_party_flags > 0:
        vote -= min(0.6, 0.3 * related_party_flags)
        reasons.append(f"{related_party_flags} related-party flag(s)")

    vote = max(-1.0, min(1.0, vote))
    if quantitative_signals >= 2:
        confidence = 0.65
    elif quantitative_signals == 1:
        confidence = 0.45
    else:
        confidence = 0.0

    if audit_opinion is not None or related_party_flags is not None:
        confidence = min(0.8, confidence + 0.1)

    return AgentVote(
        "fundamental",
        vote,
        confidence,
        "; ".join(reasons) or "CODAL fundamentals available; no directional signal",
    )


def risk_agent(company: dict) -> AgentVote:
    avail = availability(company)
    market = company["market"]
    vote = 0.0
    reasons = []
    confidence = 0.0

    if avail["codal"]:
        codal = company["codal"]
        confidence = 0.45
        guidance_note = codal.get("guidance_note") or ""
        if "cost pressure" in guidance_note:
            vote -= 0.3
            reasons.append("management flagged cost pressure")
        related_party_flags = codal.get("related_party_flags")
        if related_party_flags is not None and related_party_flags > 0:
            vote -= 0.3 * related_party_flags
            reasons.append(f"{related_party_flags} related-party flag(s)")
        if related_party_flags is None and not guidance_note:
            reasons.append("CODAL financials connected; audit/related-party parser not yet connected")
    else:
        reasons.append("no CODAL fundamentals connected yet")

    if avail["market_extended"] and market.get("price_52w_high"):
        confidence = max(confidence, 0.6)
        drawdown_pct = (market["price_52w_high"] - market["price"]) / market["price_52w_high"] * 100
        if drawdown_pct > 20:
            vote -= 0.2
            reasons.append(f"{drawdown_pct:.0f}% off 52w high")
        else:
            vote += 0.1
            reasons.append(f"only {drawdown_pct:.0f}% off 52w high")
    else:
        reasons.append("52-week range unavailable")

    vote = max(-1.0, min(1.0, vote))
    return AgentVote("risk", vote, confidence, "; ".join(reasons))


def forecast_agent(company: dict) -> AgentVote:
    avail = availability(company)
    if not avail["market_extended"]:
        return AgentVote("forecast", 0.0, 0.0, "volume/52-week range unavailable")

    market = company["market"]
    vote = 0.0
    reasons = []
    avg_volume = market.get("avg_volume_30d")
    volume_today = market.get("volume_today")
    if avg_volume not in (None, 0) and volume_today is not None:
        vol_ratio = volume_today / avg_volume
        if vol_ratio > 2:
            vote += 0.3
            reasons.append(f"volume {vol_ratio:.1f}x 30d avg — momentum building")

    high = market.get("price_52w_high")
    low = market.get("price_52w_low")
    if high is not None and low is not None and high > low:
        range_position = (market["price"] - low) / (high - low)
        range_position = max(0.0, min(1.0, range_position))
        if range_position < 0.35:
            vote += 0.2
            reasons.append(f"trading in lower {range_position:.0%} of 52w range")
        elif range_position > 0.85:
            vote -= 0.2
            reasons.append(f"trading in upper {range_position:.0%} of 52w range")

    vote = max(-1.0, min(1.0, vote))
    confidence = 0.5
    return AgentVote("forecast", vote, confidence, "; ".join(reasons) or "extended market data available; no strong signal")


def comparison_agent(company: dict) -> AgentVote:
    market = company["market"]
    pe = market.get("pe")
    sector_pe = market.get("sector_avg_pe")
    estimated_eps = market.get("estimated_eps")
    eps_value = market.get("eps_value")

    if pe is None:
        eps = eps_value if eps_value is not None else estimated_eps
        if eps is not None and eps <= 0:
            return AgentVote(
                "comparison", 0.0, 0.0,
                f"P/E unavailable because available EPS is non-positive ({eps:g})",
            )
        return AgentVote("comparison", 0.0, 0.0, "P/E unavailable")

    if sector_pe is None or sector_pe <= 0:
        return AgentVote("comparison", 0.0, 0.0, "sector P/E unavailable or non-positive")

    pe_discount_pct = (sector_pe - pe) / sector_pe * 100
    vote = max(-1.0, min(1.0, pe_discount_pct / 30))
    reasoning = (
        f"P/E {pe:.2f} vs sector {sector_pe:.2f} "
        f"({pe_discount_pct:+.0f}% {'discount' if pe_discount_pct > 0 else 'premium'})"
    )
    return AgentVote("comparison", vote, 0.65, reasoning)


ALL_AGENTS = [fundamental_agent, risk_agent, forecast_agent, comparison_agent]


def run_team(company: dict) -> list[AgentVote]:
    return [agent(company) for agent in ALL_AGENTS]
