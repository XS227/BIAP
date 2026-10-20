"""Read-time investment-mode view of the analysis ledgers for the API/frontends.

The stored ledger rows keep the conservative engine's ``call`` untouched (old rows and old clients keep working).
When ``DECISION_MODE=investment`` this module ranks each in-scope exchange with ``investment_mode.decide_ledger`` and
returns a display payload (tier, English label, top-2 positive / negative agents, flags, disclaimer) per ticker.
Nothing is written; results are cached per ledger file (mtime + size) so repeated requests are cheap.
"""
from __future__ import annotations

import re
from threading import Lock
from typing import Any, Dict, Optional

from . import investment_mode as im
from .analysis_ledger import AnalysisLedger, ledger_path

TIER_LABEL = {
    "BUY": "BUY",
    "ACCUMULATE": "ACCUMULATE",
    "HOLD": "HOLD",
    "REDUCE": "REDUCE",
    "SELL": "SELL",
    im.NO_REC: "NO RECOMMENDATION",
}
AGENT_LABEL = {
    "fundamental": "Fundamentals",
    "risk": "Risk",
    "forecast": "Price trend",
    "comparison": "Peer comparison",
    "quality": "Earnings quality",
    "liquidity": "Liquidity",
}
INSUFFICIENT_NOTICE = "Insufficient evidence"
DISCLAIMER = "Relative ranking within this exchange; not personal financial advice"
TIERS = ("BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL")

_REASON = re.compile(r"^(?P<agent>\w+) \((?P<vote>[+-]?\d+(?:\.\d+)?)\)$")
_CACHE: Dict[tuple, Dict[str, dict]] = {}
_LOCK = Lock()


def enabled(exchange_code: Optional[str] = None, mode: Optional[str] = None) -> bool:
    """Investment mode is on and (when given) ``exchange_code`` (``CC:EXCHANGE``) is inside the research scope."""
    if im.decision_mode(mode) != im.INVESTMENT:
        return False
    return exchange_code is None or im.in_scope(exchange_code)


def _agents(items) -> list[dict]:
    out = []
    for text in items:
        m = _REASON.match(text)
        if m:
            out.append({"agent": m["agent"], "vote": float(m["vote"]), "label": AGENT_LABEL.get(m["agent"], m["agent"])})
    return out


def payload(decision: im.InvestmentDecision) -> dict:
    out = {
        "mode": im.INVESTMENT,
        "tier": decision.call,
        "label": TIER_LABEL.get(decision.call, decision.call),
        "score": decision.score,
        "confidence": decision.confidence,
        "rank": decision.rank,
        "percentile": decision.percentile,
        "positionSizeHint": decision.position_size_hint,
        "positive": _agents(decision.positive_reasons),     # top 2 agents by vote x confidence
        "negative": _agents(decision.negative_reasons),     # top 2 agents by vote x confidence
        "flags": list(decision.flags),
        "peerScope": decision.peer_scope,
        "blockedBy": decision.blocked_by,
        "disclaimer": DISCLAIMER,
    }
    if "insufficient_evidence" in decision.flags or decision.blocked_by:
        out["insufficientEvidence"] = True
        out["notice"] = INSUFFICIENT_NOTICE
    return out


def cap_for_evidence(item: Optional[dict], evidence_status: Optional[str], confidence: Optional[float],
                     cfg: Optional[im.InvestmentConfig] = None) -> Optional[dict]:
    """Fresh-analysis guard: Evidence BLOCK or confidence under the threshold never keeps BUY / ACCUMULATE.

    The ranked tier comes from the stored ledger row, which can be older than the analysis shown next to it (a price
    that has since gone stale turns Evidence into BLOCK). Such a stock is capped at HOLD with the notice
    "Insufficient evidence"; HOLD / REDUCE / SELL and NO_RECOMMENDATION are left alone.
    """
    if item is None:
        return None
    floor = (cfg or im.load_config()).min_tier_confidence
    weak = str(evidence_status or "").upper() == "BLOCK" or (confidence is not None and confidence < floor)
    if not weak or item.get("tier") not in ("BUY", "ACCUMULATE"):
        return item
    flags = list(item.get("flags") or [])
    if "insufficient_evidence" not in flags:
        flags.append("insufficient_evidence")
    return {**item, "tier": "HOLD", "label": TIER_LABEL["HOLD"], "tierBeforeEvidenceCap": item["tier"],
            "positionSizeHint": None, "flags": flags, "insufficientEvidence": True, "notice": INSUFFICIENT_NOTICE}


def market_view(country: str, exchange: str) -> Dict[str, dict]:
    """{ticker: display payload} for one exchange ledger; ``{}`` when investment mode is off / out of scope / no ledger."""
    code = f"{country.upper()}:{exchange.upper()}"
    if not enabled(code):
        return {}
    path = ledger_path(country.upper(), exchange.upper())
    try:
        st = path.stat()
    except OSError:
        return {}
    stamp = (str(path), st.st_mtime_ns, st.st_size, im.load_config().__hash__())
    with _LOCK:
        hit = _CACHE.get(stamp)
    if hit is not None:
        return hit
    ledger = AnalysisLedger(country.upper(), exchange.upper())
    try:
        decisions = im.decide_ledger(ledger)
    finally:
        ledger.close()
    prefix = f"{code}:"
    view = {k[len(prefix):] if k.startswith(prefix) else k: payload(d) for k, d in decisions.items()}
    with _LOCK:
        for old in [k for k in _CACHE if k[0] == stamp[0]]:
            _CACHE.pop(old, None)
        _CACHE[stamp] = view
    return view


def tier_counts(view: Dict[str, dict]) -> Dict[str, int]:
    counts = {t: 0 for t in TIERS}
    counts[im.NO_REC] = 0
    for item in view.values():
        counts[item["tier"]] = counts.get(item["tier"], 0) + 1
    return counts
