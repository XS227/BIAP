"""
BIAP agents: fundamental analysis, risk, forecasting, comparison, technical
performance and money-flow analysis.

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

        if net_margin < 0:
            vote -= 0.4
            reasons.append(f"net margin negative ({net_margin:.1f}%)")
            if margin_delta > 0:
                vote += 0.1
                reasons.append(f"loss margin improving ({margin_delta:+.1f}pp)")
            elif margin_delta < 0:
                vote -= 0.2
                reasons.append(f"loss margin worsening ({margin_delta:+.1f}pp)")
        else:
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
        audit_opinion = codal.get("audit_opinion")
        related_party_flags = codal.get("related_party_flags")

        if "cost pressure" in guidance_note:
            vote -= 0.3
            reasons.append("management flagged cost pressure")

        if audit_opinion is not None:
            confidence = max(confidence, 0.55)
            if audit_opinion == "unqualified":
                reasons.append("audit opinion unqualified")
            else:
                vote -= 0.4
                reasons.append(f"audit opinion: {audit_opinion}")

        if related_party_flags is not None and related_party_flags > 0:
            vote -= 0.3 * related_party_flags
            reasons.append(f"{related_party_flags} related-party flag(s)")
        elif related_party_flags is None:
            reasons.append("related-party parser not yet connected")

        if audit_opinion is None and not guidance_note and related_party_flags is None:
            reasons.append("CODAL financials connected; audit opinion unavailable")
    else:
        reasons.append("no CODAL fundamentals connected yet")

    high = market.get("price_52w_high")
    price = market.get("price")
    if high and price is not None:
        confidence = max(confidence, 0.6)
        drawdown_pct = (high - price) / high * 100
        if drawdown_pct > 20:
            vote -= 0.2
            reasons.append(f"{drawdown_pct:.0f}% off 52w high")
        else:
            vote += 0.1
            reasons.append(f"only {drawdown_pct:.0f}% off 52w high")
    else:
        reasons.append("52-week range unavailable")

    perf = market.get("tindex_performance") or {}
    max_drawdown = perf.get("max_drawdown")
    volatility = perf.get("volatility")
    if max_drawdown is not None:
        confidence = max(confidence, 0.65)
        if max_drawdown <= -35:
            vote -= 0.25
            reasons.append(f"max drawdown {max_drawdown:.1f}%")
    if volatility is not None:
        confidence = max(confidence, 0.65)
        if volatility >= 50:
            vote -= 0.15
            reasons.append(f"high annualized volatility {volatility:.1f}%")

    vote = max(-1.0, min(1.0, vote))
    return AgentVote("risk", vote, confidence, "; ".join(reasons))


def forecast_agent(company: dict) -> AgentVote:
    market = company["market"]
    perf = market.get("tindex_performance") or {}
    vote = 0.0
    reasons = []
    signals = 0

    avg_volume = market.get("avg_volume_30d")
    volume_today = market.get("volume_today")
    if avg_volume not in (None, 0) and volume_today is not None:
        signals += 1
        vol_ratio = volume_today / avg_volume
        if vol_ratio > 2:
            vote += 0.3
            reasons.append(f"volume {vol_ratio:.1f}x 30d avg")

    r1m = perf.get("return_1m")
    r3m = perf.get("return_3m")
    r6m = perf.get("return_6m")
    if r1m is not None and r3m is not None:
        signals += 1
        if r1m > 0 and r3m > 0:
            vote += 0.25
            reasons.append(f"positive 1m/3m momentum ({r1m:+.1f}%, {r3m:+.1f}%)")
        elif r1m < 0 and r3m < 0:
            vote -= 0.25
            reasons.append(f"negative 1m/3m momentum ({r1m:+.1f}%, {r3m:+.1f}%)")
    if r6m is not None:
        signals += 1
        reasons.append(f"6m return {r6m:+.1f}%")

    high = market.get("price_52w_high")
    low = market.get("price_52w_low")
    price = market.get("price")
    if high is not None and low is not None and price is not None and high > low:
        signals += 1
        range_position = max(0.0, min(1.0, (price - low) / (high - low)))
        if range_position < 0.35:
            vote += 0.15
            reasons.append(f"lower {range_position:.0%} of 52w range")
        elif range_position > 0.85:
            vote -= 0.15
            reasons.append(f"upper {range_position:.0%} of 52w range")

    if signals == 0:
        return AgentVote("forecast", 0.0, 0.0, "verified momentum/history unavailable")
    vote = max(-1.0, min(1.0, vote))
    return AgentVote("forecast", vote, min(0.75, 0.35 + 0.1 * signals), "; ".join(reasons) or "no strong momentum signal")


def comparison_agent(company: dict) -> AgentVote:
    market = company["market"]
    pe = market.get("pe")
    sector_pe = market.get("sector_avg_pe")
    estimated_eps = market.get("estimated_eps")
    eps_value = market.get("eps_value")

    if pe is None:
        eps = eps_value if eps_value is not None else estimated_eps
        if eps is not None and eps <= 0:
            return AgentVote("comparison", 0.0, 0.0, f"P/E unavailable because available EPS is non-positive ({eps:g})")
        return AgentVote("comparison", 0.0, 0.0, "P/E unavailable")

    if sector_pe is None or sector_pe <= 0:
        return AgentVote("comparison", 0.0, 0.0, "sector P/E unavailable or non-positive")

    pe_discount_pct = (sector_pe - pe) / sector_pe * 100
    vote = max(-1.0, min(1.0, pe_discount_pct / 30))
    reasoning = f"P/E {pe:.2f} vs sector {sector_pe:.2f} ({pe_discount_pct:+.0f}% {'discount' if pe_discount_pct > 0 else 'premium'})"
    return AgentVote("comparison", vote, 0.65, reasoning)


def technical_agent(company: dict) -> AgentVote:
    perf = (company.get("market") or {}).get("tindex_performance") or {}
    values = [perf.get("return_1w"), perf.get("return_1m"), perf.get("return_3m"), perf.get("return_1y")]
    if all(v is None for v in values):
        return AgentVote("technical", 0.0, 0.0, "verified multi-horizon performance unavailable")

    vote = 0.0
    reasons = []
    weights = (("1w", perf.get("return_1w"), 0.15), ("1m", perf.get("return_1m"), 0.30), ("3m", perf.get("return_3m"), 0.35), ("1y", perf.get("return_1y"), 0.20))
    observed = 0
    for label, value, weight in weights:
        if value is None:
            continue
        observed += 1
        direction = max(-1.0, min(1.0, value / 20.0))
        vote += weight * direction
        reasons.append(f"{label} {value:+.1f}%")

    position = perf.get("range_52w_position")
    if position is not None:
        observed += 1
        if position >= 90:
            vote -= 0.10
            reasons.append(f"{position:.0f}% through 52w range")
        elif position <= 20:
            vote += 0.10
            reasons.append(f"{position:.0f}% through 52w range")

    return AgentVote("technical", max(-1.0, min(1.0, vote)), min(0.75, 0.35 + 0.08 * observed), "; ".join(reasons))


def flow_agent(company: dict) -> AgentVote:
    flow = (company.get("market") or {}).get("tindex_flow") or {}
    retail_net = flow.get("retail_net")
    buy_pc = flow.get("buy_per_capita")
    sell_pc = flow.get("sell_per_capita")
    if retail_net is None and (buy_pc is None or sell_pc is None):
        return AgentVote("flow", 0.0, 0.0, "verified retail/institutional flow unavailable")

    vote = 0.0
    reasons = []
    signals = 0
    if retail_net is not None:
        signals += 1
        if retail_net > 0:
            vote += 0.35
            reasons.append("net retail inflow")
        elif retail_net < 0:
            vote -= 0.35
            reasons.append("net retail outflow")
    if buy_pc is not None and sell_pc not in (None, 0):
        signals += 1
        ratio = buy_pc / sell_pc
        if ratio >= 1.25:
            vote += 0.30
            reasons.append(f"buy/sell per-capita {ratio:.2f}x")
        elif ratio <= 0.80:
            vote -= 0.30
            reasons.append(f"buy/sell per-capita {ratio:.2f}x")

    return AgentVote("flow", max(-1.0, min(1.0, vote)), min(0.70, 0.45 + 0.10 * signals), "; ".join(reasons))


ALL_AGENTS = [fundamental_agent, risk_agent, forecast_agent, comparison_agent, technical_agent, flow_agent]


def run_team(company: dict) -> list[AgentVote]:
    return [agent(company) for agent in ALL_AGENTS]
