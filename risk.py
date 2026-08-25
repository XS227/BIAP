"""Risk policy for BIAP order intents.

The policy is deliberately conservative and independent from the analysis
agents. It can reject an otherwise valid BUY/SELL intent before anything reaches
a broker adapter.

Configuration is via environment variables so deployment can tighten limits
without code changes. AUTO remains disabled in execution.py regardless of these
settings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class RiskPolicy:
    kill_switch: bool
    max_quantity: int
    max_order_notional: float
    max_daily_notional: float
    max_limit_deviation_pct: float
    min_buy_score: float
    max_sell_score: float


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: list[str]
    checks: dict[str, bool]

    def to_dict(self) -> dict:
        return asdict(self)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def load_policy() -> RiskPolicy:
    return RiskPolicy(
        kill_switch=_env_bool("BIAP_KILL_SWITCH", False),
        max_quantity=max(1, _env_int("BIAP_MAX_ORDER_QUANTITY", 100_000)),
        max_order_notional=max(0.0, _env_float("BIAP_MAX_ORDER_NOTIONAL", 2_000_000_000.0)),
        max_daily_notional=max(0.0, _env_float("BIAP_MAX_DAILY_NOTIONAL", 5_000_000_000.0)),
        max_limit_deviation_pct=max(0.0, _env_float("BIAP_MAX_LIMIT_DEVIATION_PCT", 5.0)),
        min_buy_score=max(-1.0, min(1.0, _env_float("BIAP_MIN_BUY_SCORE", 0.10))),
        max_sell_score=max(-1.0, min(1.0, _env_float("BIAP_MAX_SELL_SCORE", -0.10))),
    )


def evaluate_order_risk(
    *,
    side: str,
    quantity: int,
    limit_price: Optional[float],
    reference_price: Optional[float],
    recommendation_score: float,
    daily_notional_used: float,
    policy: Optional[RiskPolicy] = None,
) -> RiskDecision:
    p = policy or load_policy()
    reasons: list[str] = []
    checks: dict[str, bool] = {}

    checks["killSwitchOff"] = not p.kill_switch
    if p.kill_switch:
        reasons.append("global kill switch is active")

    checks["quantityWithinLimit"] = quantity <= p.max_quantity
    if not checks["quantityWithinLimit"]:
        reasons.append(f"quantity exceeds max {p.max_quantity}")

    order_notional = quantity * limit_price if limit_price is not None else None
    checks["orderNotionalWithinLimit"] = (
        order_notional is None or order_notional <= p.max_order_notional
    )
    if not checks["orderNotionalWithinLimit"]:
        reasons.append(f"order notional exceeds max {p.max_order_notional:.0f}")

    projected_daily = daily_notional_used + (order_notional or 0.0)
    checks["dailyNotionalWithinLimit"] = projected_daily <= p.max_daily_notional
    if not checks["dailyNotionalWithinLimit"]:
        reasons.append(f"projected daily notional exceeds max {p.max_daily_notional:.0f}")

    deviation_ok = True
    if limit_price is not None and reference_price is not None and reference_price > 0:
        deviation_pct = abs(limit_price / reference_price - 1.0) * 100.0
        deviation_ok = deviation_pct <= p.max_limit_deviation_pct
        if not deviation_ok:
            reasons.append(
                f"limit price deviates {deviation_pct:.2f}% from reference; "
                f"max is {p.max_limit_deviation_pct:.2f}%"
            )
    checks["limitPriceDeviationWithinLimit"] = deviation_ok

    recommendation_ok = True
    if side == "BUY" and recommendation_score < p.min_buy_score:
        recommendation_ok = False
        reasons.append(
            f"BUY score {recommendation_score:.3f} below minimum {p.min_buy_score:.3f}"
        )
    elif side == "SELL" and recommendation_score > p.max_sell_score:
        recommendation_ok = False
        reasons.append(
            f"SELL score {recommendation_score:.3f} above maximum {p.max_sell_score:.3f}"
        )
    checks["recommendationStrengthAccepted"] = recommendation_ok

    return RiskDecision(
        allowed=all(checks.values()),
        reasons=reasons,
        checks=checks,
    )


def policy_snapshot(policy: Optional[RiskPolicy] = None) -> dict:
    return asdict(policy or load_policy())
