"""
BIAP-agenter: fundamental analyse, risiko, forecasting, sammenligning.

Each agent reads the normalized company record (see data_sample.py /
company_builder.py) and returns a vote in [-1, 1] (SELL..BUY) plus a
confidence in [0, 1] and a short reasoning string. Kiasha (kiasha.py)
combines these votes -- agents don't decide anything themselves.

Not every company record carries every field. A record built from live
price-only data (company_builder.build_company_from_quote) has no CODAL
fundamentals and no extended market data (52-week range, P/E, volume) yet
-- see `data_available`/`availability()`. Agents that need missing data
return a neutral, zero-confidence vote with a reasoning string that says
exactly what's missing, instead of guessing or crashing.
"""

from dataclasses import dataclass

from company_builder import availability


@dataclass
class AgentVote:
    agent: str
    vote: float        # -1 (strong sell) .. +1 (strong buy)
    confidence: float  # 0..1
    reasoning: str


def fundamental_agent(company: dict) -> AgentVote:
    avail = availability(company)
    if not avail["codal"]:
        return AgentVote("fundamental", 0.0, 0.0, "no CODAL fundamentals connected yet")

    codal = company["codal"]
    margin_delta = codal["net_margin_pct"] - codal["net_margin_prev_pct"]
    vote = 0.0
    reasons = []

    if codal["revenue_yoy_pct"] > 10:
        vote += 0.4
        reasons.append(f"revenue +{codal['revenue_yoy_pct']}% YoY")
    if margin_delta > 0:
        vote += 0.3
        reasons.append(f"margin improving ({margin_delta:+.1f}pp)")
    else:
        vote -= 0.2
        reasons.append(f"margin declining ({margin_delta:+.1f}pp)")
    if codal["audit_opinion"] != "unqualified":
        vote -= 0.5
        reasons.append(f"audit opinion: {codal['audit_opinion']}")

    vote = max(-1.0, min(1.0, vote))
    confidence = 0.7 if codal["related_party_flags"] == 0 else 0.4
    return AgentVote("fundamental", vote, confidence, "; ".join(reasons))


def risk_agent(company: dict) -> AgentVote:
    avail = availability(company)
    market = company["market"]
    vote = 0.0
    reasons = []
    confidence = 0.0

    if avail["codal"]:
        codal = company["codal"]
        confidence = 0.6
        if "cost pressure" in codal.get("guidance_note", ""):
            vote -= 0.3
            reasons.append("management flagged cost pressure")
        if codal["related_party_flags"] > 0:
            vote -= 0.3 * codal["related_party_flags"]
            reasons.append(f"{codal['related_party_flags']} related-party flag(s)")
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
        reasons.append("no 52-week range yet (extended market data not connected)")

    vote = max(-1.0, min(1.0, vote))
    return AgentVote("risk", vote, confidence, "; ".join(reasons))


def forecast_agent(company: dict) -> AgentVote:
    avail = availability(company)
    if not avail["market_extended"]:
        return AgentVote(
            "forecast", 0.0, 0.0,
            "no volume/52-week range data yet (extended market data not connected)",
        )

    market = company["market"]
    vote = 0.0
    reasons = []

    vol_ratio = market["volume_today"] / market["avg_volume_30d"]
    if vol_ratio > 2:
        vote += 0.3
        reasons.append(f"volume {vol_ratio:.1f}x 30d avg — momentum building")
    range_position = (market["price"] - market["price_52w_low"]) / (
        market["price_52w_high"] - market["price_52w_low"]
    )
    if range_position < 0.35:
        vote += 0.2
        reasons.append(f"trading in lower {range_position:.0%} of 52w range")
    elif range_position > 0.85:
        vote -= 0.2
        reasons.append(f"trading in upper {range_position:.0%} of 52w range")

    vote = max(-1.0, min(1.0, vote))
    confidence = 0.5  # forecasting is inherently the least certain
    return AgentVote("forecast", vote, confidence, "; ".join(reasons))


def comparison_agent(company: dict) -> AgentVote:
    avail = availability(company)
    market = company["market"]
    if not avail["market_extended"] or market.get("pe") is None:
        return AgentVote("comparison", 0.0, 0.0, "no P/E data yet (extended market data not connected)")

    pe_discount_pct = (market["sector_avg_pe"] - market["pe"]) / market["sector_avg_pe"] * 100
    vote = max(-1.0, min(1.0, pe_discount_pct / 30))
    reasoning = (
        f"P/E {market['pe']} vs sector avg {market['sector_avg_pe']} "
        f"({pe_discount_pct:+.0f}% {'discount' if pe_discount_pct > 0 else 'premium'})"
    )
    confidence = 0.65
    return AgentVote("comparison", vote, confidence, reasoning)


ALL_AGENTS = [fundamental_agent, risk_agent, forecast_agent, comparison_agent]


def run_team(company: dict) -> list[AgentVote]:
    return [agent(company) for agent in ALL_AGENTS]
