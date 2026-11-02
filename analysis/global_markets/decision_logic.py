"""Decision-logic version switch and engine labelling.

``DECISION_LOGIC_VERSION`` selects the conservative-engine decision logic:

* ``v1`` (default, and the fallback for any unknown value): the logic that was live on 2026-10-30. It is what the
  frozen paper portfolio (``research/paper_portfolio_2026-10-20.json``) and the paper's Chapter 4 measure and it must not
  change. The investment mode (``investment_mode.py``) is **never** switched by this setting.
* ``v2``: fixes P1.10 (abstaining agents carry no weight), P1.3 (Agent 8 disagreement rule), graded price freshness and
  related items from ``docs/BIAP_FIX_PLAN.md``. Opt-in; every difference is listed in
  ``docs/CHANGELOG_DECISION_LOGIC.md``.

Engines (P1.11): ``conservative`` = absolute thresholds + Agent 8 governance (the stored ``call``); ``investment`` =
rank-based tiers of the investment mode. ``engines_block`` gives every API payload an explicit, labelled description of
both so no client has to guess which score or label belongs to which engine.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional

V1 = "v1"
V2 = "v2"
VALID_VERSIONS = (V1, V2)

ENGINE_CONSERVATIVE = "conservative"
ENGINE_INVESTMENT = "investment"

ENGINE_LABEL = {
    ENGINE_CONSERVATIVE: "Conservative check",
    ENGINE_INVESTMENT: "Investment ranking",
}
ENGINE_DESCRIPTION = {
    ENGINE_CONSERVATIVE: "Absolute thresholds and Agent 8 governance; a stock can be left without a recommendation.",
    ENGINE_INVESTMENT: "Relative ranking within this exchange (BUY / ACCUMULATE / HOLD / REDUCE / SELL).",
}


def logic_version(value: Optional[str] = None) -> str:
    """Configured decision-logic version; anything but ``v2`` means ``v1`` (the frozen, paper-measured logic)."""
    raw = os.environ.get("DECISION_LOGIC_VERSION") if value is None else value
    text = str(raw or "").strip().lower()
    return V2 if text == V2 else V1


def is_v2(value: Optional[str] = None) -> bool:
    return logic_version(value) == V2


def _round(value: Any, digits: int = 6) -> Optional[float]:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def engines_block(result: Mapping[str, Any], investment: Optional[Mapping[str, Any]]) -> dict:
    """Both engines side by side for one analysed stock (additive API field ``engines``).

    ``displayed`` names the engine whose label a client shows as the decision: the investment tier when one exists,
    otherwise the conservative call. The numbers are never mixed: ``conservative.score`` is the fresh analysis score,
    ``investment.score`` is the ranking score of the stored ledger row.
    """
    conservative = {
        "engine": ENGINE_CONSERVATIVE,
        "label": ENGINE_LABEL[ENGINE_CONSERVATIVE],
        "description": ENGINE_DESCRIPTION[ENGINE_CONSERVATIVE],
        "call": result.get("call"),
        "score": _round(result.get("score")),
        "confidence": _round(result.get("confidence")),
        "logicVersion": logic_version(),
    }
    block: dict = {"conservative": conservative, "displayed": ENGINE_CONSERVATIVE, "investment": None}
    if investment:
        block["investment"] = {
            "engine": ENGINE_INVESTMENT,
            "label": ENGINE_LABEL[ENGINE_INVESTMENT],
            "description": ENGINE_DESCRIPTION[ENGINE_INVESTMENT],
            "tier": investment.get("tier"),
            "score": _round(investment.get("score")),
            "confidence": _round(investment.get("confidence")),
            "rank": investment.get("rank"),
            "percentile": _round(investment.get("percentile")),
        }
        block["displayed"] = ENGINE_INVESTMENT
    return block
