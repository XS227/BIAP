"""Investment decision mode (``DECISION_MODE=investment``): ranked BUY / ACCUMULATE / HOLD / REDUCE / SELL.

``DECISION_MODE=conservative`` (the default) is the existing absolute-threshold engine
(``service._call`` + Agent 8 governance in ``governance.py``) and is not touched by this module.
The investment mode is opt-in and works on a *batch* of analysed stocks, because tiers are relative:

  a. an agent without data is *unknown*: left out of the score and confidence means; confidence is
     reduced only when fewer than ``min_agents_full_confidence`` (4) agents have data, and fewer than
     ``min_agents_hard_block`` (3) is a hard block;
  b. risk vote = percentile of the risk metrics inside the same exchange (and sector when the sector has
     >= ``risk_sector_min_peers`` peers), mapped to [-1, +1]; the median-risk stock gets ~0;
  c. comparison vote: native sector peers (>= 8) -> exchange-wide sector -> same sector across all covered
     markets; ``peer_scope`` records which; PEG / growth-adjusted P/E is blended in where growth exists;
  d. per market, recomputed every run: BUY top 10% and score > 0 and >= 4 agents with data, ACCUMULATE top 25% and
     score > 0, REDUCE bottom 25% and score < 0, SELL bottom 10% and score < 0 and >= 4 agents with data, else HOLD
     (all in ``InvestmentConfig``). A top-10% / bottom-10% stock with only 3 agents falls to ACCUMULATE / REDUCE;
     there is no score floor besides the sign;
  e. high-confidence disagreement downgrades one tier (BUY->ACCUMULATE, SELL->REDUCE) and sets ``agents_disagree``;
  f. the PR #52 BUY gates (distress not LOW_RISK, peer group < 8, no independent non-comparison signal,
     evidence WARN) are downgrade flags (BUY->ACCUMULATE); soft flags together move a stock at most one tier.
     Distress UNKNOWN (INSUFFICIENT_DATA: missing inputs) is not a finding: it only sets the info flag ``distress_unknown``;
     only ELEVATED_RISK / HIGH_RISK set the soft ``distress_not_low_risk`` flag;
     Hard blocks stay only for: distress ``positive_block`` (on BUY/ACCUMULATE), evidence BLOCK, < 3 agents with data;
  g. every decision carries tier, score, confidence, position_size_hint, top-2 positive / negative agents, flags, peer_scope.

Pure functions only: no I/O, no provider calls, no production state (``decide_ledger`` only reads a ledger).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, fields, replace
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CONSERVATIVE = "conservative"
INVESTMENT = "investment"
VALID_MODES = (CONSERVATIVE, INVESTMENT)
TIERS = ("SELL", "REDUCE", "HOLD", "ACCUMULATE", "BUY")     # worst -> best
NO_REC = "NO_RECOMMENDATION"
AGENTS = ("fundamental", "risk", "forecast", "comparison", "quality", "liquidity")

SOFT_DOWNGRADE_FLAGS_DEFAULT = (
    "agents_disagree", "distress_not_low_risk", "peer_group_small", "no_independent_signal", "evidence_warn",
    "widened_peers",
)

# Research-paper scope (frozen 2026-10-19): only these exchanges take part in investment-mode runs, reports and the
# paper. Every other exchange is HIDDEN, not deleted: its adapters, ledgers and data stay untouched. One switch
# re-enables them: ``BIAP_INVESTMENT_SCOPE=all`` (or ``InvestmentConfig(restrict_to_markets=False)``).
# DE:XETRA and DE:FRANKFURT are one market (``MARKET_GROUPS``): ranked together, deduped by ISIN.
INVESTMENT_MODE_MARKETS = (
    "US:NASDAQ", "US:NYSE", "GB:LSE", "IT:EURONEXT_MILAN", "SE:NASDAQ_STOCKHOLM", "NO:EURONEXT_OSLO",
    "DE:XETRA", "DE:FRANKFURT", "FR:EURONEXT_PARIS", "NL:EURONEXT_AMSTERDAM", "FI:NASDAQ_HELSINKI", "ES:BME_MADRID",
)
SCOPE_ENV = "BIAP_INVESTMENT_SCOPE"          # "restricted" (default) | "all"


def scope_restricted(value: Optional[str] = None) -> bool:
    """True = only ``INVESTMENT_MODE_MARKETS`` are in scope (default); ``all`` re-enables the hidden markets."""
    raw = (value if value is not None else os.environ.get(SCOPE_ENV, "restricted")).strip().lower()
    return raw != "all"


def in_scope(exchange: str, restricted: Optional[bool] = None) -> bool:
    """``exchange`` is ``CC:EXCHANGE`` (e.g. ``US:NYSE``)."""
    restricted = scope_restricted() if restricted is None else restricted
    return (not restricted) or exchange in INVESTMENT_MODE_MARKETS


# Listings of one issuer on several venues are ranked as ONE market (deduped by ISIN).
MARKET_GROUPS = {"DE:XETRA": "DE", "DE:FRANKFURT": "DE"}


def market_of(exchange: str) -> str:
    return MARKET_GROUPS.get(exchange, exchange)


@dataclass(frozen=True)
class InvestmentConfig:
    """Every threshold of the investment mode. Override with ``BIAP_INVESTMENT_CONFIG='{"buy_min_score": 0.15}'``."""

    # an agent with confidence below this has no usable data (core agents emit 0.0 unavailable / 0.25 abstaining)
    data_min_confidence: float = 0.30
    min_agents_hard_block: int = 3
    min_agents_full_confidence: int = 4
    # relative tiers (fractions of the analysed stocks of one exchange) + absolute score floors
    buy_top_fraction: float = 0.10
    accumulate_top_fraction: float = 0.25
    reduce_bottom_fraction: float = 0.25
    sell_bottom_fraction: float = 0.10
    buy_min_score: float = 0.0               # strict: score > 0 (the 0.10 floor was removed 2026-10-19)
    accumulate_min_score: float = 0.0
    reduce_max_score: float = 0.0
    sell_max_score: float = 0.0              # strict: score < 0 (symmetric to BUY)
    buy_min_agents: int = 4                  # BUY / SELL need at least this many of the 6 agents with data
    sell_min_agents: int = 4
    restrict_to_markets: bool = True         # False = hidden markets back in scope (same as BIAP_INVESTMENT_SCOPE=all)
    # risk agent
    risk_sector_min_peers: int = 8
    risk_min_metrics: int = 2
    # comparison agent
    peer_min_group: int = 8
    widen_peers: bool = True                 # False = native peer group only (used to measure what widening adds)
    discount_votes: Tuple[Tuple[float, float], ...] = ((0.30, 0.6), (0.15, 0.35), (-0.15, 0.0), (-0.30, -0.3))
    premium_floor_vote: float = -0.5         # discount <= -30%
    comparison_confidence: float = 0.65      # same as the core comparison agent
    comparison_confidence_global: float = 0.55
    peg_growth_cap_pct: float = 50.0
    peg_growth_floor_pct: float = 1.0
    # widened-peer guard: a BUY whose comparison vote rests on widened peers needs another agent this strong
    widened_guard: bool = True
    widened_guard_vote: float = 0.35
    widened_guard_confidence: float = 0.55
    # disagreement (same constants as agents.evidence_agent)
    disagree_confidence: float = 0.55
    disagree_positive: float = 0.35
    disagree_negative: float = -0.35
    # position size hint from decision confidence
    size_high: float = 0.65
    size_medium: float = 0.50
    soft_downgrade_flags: Tuple[str, ...] = SOFT_DOWNGRADE_FLAGS_DEFAULT
    buy_distress_ok: Tuple[str, ...] = ("LOW_RISK", "NOT_APPLICABLE")
    # missing data (e.g. no operating cash flow) is not a distress finding: info flag ``distress_unknown``, no downgrade
    distress_unknown: Tuple[Optional[str], ...] = ("INSUFFICIENT_DATA", "NOT_RUN", "UNKNOWN", None)


DEFAULT_CONFIG = InvestmentConfig()


def load_config(raw: Optional[str] = None) -> InvestmentConfig:
    """Default config with overrides from ``BIAP_INVESTMENT_CONFIG`` (JSON object); bad input -> defaults."""
    text = raw if raw is not None else os.environ.get("BIAP_INVESTMENT_CONFIG", "")
    if not text.strip():
        return DEFAULT_CONFIG
    try:
        data = json.loads(text)
    except ValueError:
        return DEFAULT_CONFIG
    if not isinstance(data, dict):
        return DEFAULT_CONFIG
    known = {f.name for f in fields(InvestmentConfig)}
    over: Dict[str, Any] = {}
    for key, value in data.items():
        if key in known:
            over[key] = tuple(tuple(x) if isinstance(x, list) else x for x in value) if isinstance(value, list) else value
    return replace(DEFAULT_CONFIG, **over)


def decision_mode(value: Optional[str] = None) -> str:
    """Configured decision mode; unknown or unset values fall back to ``conservative``."""
    raw = (value if value is not None else os.environ.get("DECISION_MODE", CONSERVATIVE)).strip().lower()
    return raw if raw in VALID_MODES else CONSERVATIVE


@dataclass(frozen=True)
class Candidate:
    """One analysed stock, reduced to what the investment decision needs."""

    key: str                                    # unique id inside the batch, e.g. "XETRA:SAP"
    exchange: str
    sector: Optional[str]
    signals: Mapping[str, Tuple[float, float]]  # agent -> (vote, confidence), raw agent output
    evidence_status: str = "PASS"               # PASS / WARN / BLOCK
    evidence_multiplier: float = 1.0
    positive_block: bool = False                # Agent 9 distress hard block
    distress_status: Optional[str] = None
    isin: Optional[str] = None
    pe: Optional[float] = None
    growth_pct: Optional[float] = None          # earnings growth, else revenue growth
    peer_count: Optional[int] = None            # native comparison-agent peer group
    risk_metrics: Mapping[str, Optional[float]] = field(default_factory=dict)
    statement_coverage: Optional[float] = None  # evidence coverage 0..1; None = unknown (no flag, no penalty)


@dataclass(frozen=True)
class InvestmentDecision:
    key: str
    call: str                                   # BUY / ACCUMULATE / HOLD / REDUCE / SELL / NO_RECOMMENDATION
    score: Optional[float]
    confidence: Optional[float]
    agents_with_data: int
    rank: Optional[int]                         # 1 = best in the exchange
    percentile: Optional[float]                 # 0.0 = best
    position_size_hint: Optional[str]
    flags: Tuple[str, ...] = ()
    peer_scope: str = "none"
    positive_reasons: Tuple[str, ...] = ()
    negative_reasons: Tuple[str, ...] = ()
    reason: str = ""
    blocked_by: Optional[str] = None
    tier_before_flags: Optional[str] = None
    used_votes: Mapping[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------------- small helpers
def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def has_data(signal: Tuple[float, float], cfg: InvestmentConfig = DEFAULT_CONFIG) -> bool:
    return float(signal[1]) >= cfg.data_min_confidence


def midrank_percentile(value: float, cohort: Sequence[float]) -> float:
    """Share of the cohort below ``value`` (ties count half), in [0, 1]; a cohort of one gives 0.5."""
    n = len(cohort)
    if n <= 1:
        return 0.5
    below = sum(1 for other in cohort if other < value)
    equal = sum(1 for other in cohort if other == value)
    return (below + 0.5 * equal) / n


def _norm_sector(sector: Optional[str]) -> Optional[str]:
    s = (sector or "").strip().lower()
    return s or None


def position_size_hint(confidence: float, cfg: InvestmentConfig = DEFAULT_CONFIG) -> str:
    if confidence >= cfg.size_high:
        return "high"
    if confidence >= cfg.size_medium:
        return "medium"
    return "small"


# ---------------------------------------------------------------------------------- (b) risk agent
def _risk_badness(metrics: Mapping[str, Optional[float]]) -> Dict[str, float]:
    """Metric -> value where HIGHER = riskier. Missing metrics are simply absent."""
    out: Dict[str, float] = {}
    vol, dd = metrics.get("volatility_pct"), metrics.get("drawdown_pct")
    if vol is not None:
        out["volatility"] = float(vol)
    if dd is not None:
        out["drawdown"] = abs(float(dd))
    liab, eq = metrics.get("liabilities"), metrics.get("equity")
    if liab is not None and eq is not None:
        out["leverage"] = float(liab) / float(eq) if float(eq) > 0 else 1e9      # negative equity = worst
    debt, ocf = metrics.get("debt"), metrics.get("operating_cash_flow")
    if debt is not None and ocf is not None and float(debt) > 0:
        out["debt_cover"] = float(debt) / float(ocf) if float(ocf) > 0 else 1e9
    cr = metrics.get("current_ratio")
    if cr is not None:
        out["liquidity_ratio"] = -float(cr)
    return out


def relative_risk_votes(candidates: Sequence[Candidate], cfg: InvestmentConfig = DEFAULT_CONFIG) -> Dict[str, float]:
    """key -> risk vote in [-1, +1] (high = safer than the cohort), cohort = exchange, or sector if >= 8 peers.

    Uses the underlying risk metrics (volatility, drawdown, leverage, debt/OCF, current ratio): each is turned
    into a percentile inside the cohort, the available ones are averaged, and the average is ranked again so the
    median-risk stock gets ~0. Stocks with fewer than ``risk_min_metrics`` metrics fall back to the percentile
    of the raw risk vote. Only stocks whose risk agent has data take part.
    """
    pool = [c for c in candidates if "risk" in c.signals and has_data(c.signals["risk"], cfg)]
    out: Dict[str, float] = {}
    by_exchange: Dict[str, List[Candidate]] = {}
    for c in pool:
        by_exchange.setdefault(c.exchange, []).append(c)
    for members in by_exchange.values():
        by_sector: Dict[str, List[Candidate]] = {}
        for c in members:
            sec = _norm_sector(c.sector)
            if sec:
                by_sector.setdefault(sec, []).append(c)
        groups: List[List[Candidate]] = []
        loose = list(members)
        for sec, grp in by_sector.items():
            if len(grp) >= cfg.risk_sector_min_peers:
                groups.append(grp)
                loose = [c for c in loose if c not in grp]
        if loose:
            groups.append(loose)
        for grp in groups:
            _vote_group(grp, out, cfg)
    return out


def _vote_group(grp: Sequence[Candidate], out: Dict[str, float], cfg: InvestmentConfig) -> None:
    bad = {c.key: _risk_badness(c.risk_metrics) for c in grp}
    names = ("volatility", "drawdown", "leverage", "debt_cover", "liquidity_ratio")
    cohort = {n: [b[n] for b in bad.values() if n in b] for n in names}
    composite: Dict[str, float] = {}
    for c in grp:
        b = bad[c.key]
        if len(b) >= cfg.risk_min_metrics:
            composite[c.key] = sum(midrank_percentile(v, cohort[n]) for n, v in b.items()) / len(b)
    comp_values = list(composite.values())
    for c in grp:
        if c.key in composite:
            out[c.key] = _clamp(1.0 - 2.0 * midrank_percentile(composite[c.key], comp_values))
    raw_only = [c for c in grp if c.key not in composite]
    raw_values = [c.signals["risk"][0] for c in raw_only]
    for c in raw_only:
        out[c.key] = _clamp(2.0 * midrank_percentile(c.signals["risk"][0], raw_values) - 1.0)


# ---------------------------------------------------------------------------------- (c) comparison agent
def _discount_vote(discount: float, cfg: InvestmentConfig) -> float:
    """Same mapping as ``core_agents.comparison_agent``: discount = (benchmark - metric) / benchmark."""
    for bound, vote in cfg.discount_votes:
        if discount >= bound:
            return vote
    return cfg.premium_floor_vote


def peg(c: Candidate, cfg: InvestmentConfig) -> Optional[float]:
    if c.pe is None or c.pe <= 0 or c.growth_pct is None or c.growth_pct <= 0:
        return None
    return c.pe / _clamp(c.growth_pct, cfg.peg_growth_floor_pct, cfg.peg_growth_cap_pct)


def _median_without(values: List[Tuple[str, float]], key: str) -> Tuple[Optional[float], int]:
    rest = [v for k, v in values if k != key]
    return (median(rest), len(rest)) if rest else (None, 0)


def comparison_votes(
    candidates: Sequence[Candidate], cfg: InvestmentConfig = DEFAULT_CONFIG
) -> Dict[str, Tuple[Optional[float], float, str]]:
    """key -> (vote or None, confidence, peer_scope) for every candidate.

    peer_scope: ``scan_sector`` (native, >= 8 same-sector peers) | ``exchange_sector`` | ``global_sector`` |
    ``small_group`` (native 3-7 peers, nothing wider available) | ``book_value`` (P/B fallback) | ``none``.
    Widening needs the stock's sector; pools use the P/E of analysed stocks (one row per ISIN across markets).
    """
    by_ex_sector: Dict[Tuple[str, str], List[Tuple[str, float]]] = {}
    by_sector: Dict[str, List[Tuple[str, float]]] = {}
    peg_ex: Dict[Tuple[str, str], List[Tuple[str, float]]] = {}
    peg_sector: Dict[str, List[Tuple[str, float]]] = {}
    seen_global = set()
    for c in candidates:
        sec = _norm_sector(c.sector)
        if not sec or c.pe is None or c.pe <= 0:
            continue
        by_ex_sector.setdefault((c.exchange, sec), []).append((c.key, c.pe))
        ident = c.isin or c.key
        g = peg(c, cfg)
        if g is not None:
            peg_ex.setdefault((c.exchange, sec), []).append((c.key, g))
        if ident not in seen_global:
            seen_global.add(ident)
            by_sector.setdefault(sec, []).append((c.key, c.pe))
            if g is not None:
                peg_sector.setdefault(sec, []).append((c.key, g))

    out: Dict[str, Tuple[Optional[float], float, str]] = {}
    for c in candidates:
        raw = c.signals.get("comparison")
        raw_ok = raw is not None and has_data(raw, cfg)
        sec = _norm_sector(c.sector)
        if c.pe is None or c.pe <= 0 or not sec:
            if not raw_ok:
                out[c.key] = (None, 0.0, "none")
            elif c.pe is None or c.pe <= 0:
                out[c.key] = (raw[0], raw[1], "book_value")     # loss-maker: the agent's P/B comparison
            else:
                out[c.key] = (raw[0], raw[1], "small_group")    # no sector, so it cannot be widened
            continue
        if raw_ok and (c.peer_count or 0) >= cfg.peer_min_group:
            out[c.key] = (raw[0], raw[1], "scan_sector")
            continue
        chosen = None
        for scope, pe_pool, peg_pool, conf in () if not cfg.widen_peers else (
            ("exchange_sector", by_ex_sector.get((c.exchange, sec), []), peg_ex.get((c.exchange, sec), []),
             cfg.comparison_confidence),
            ("global_sector", by_sector.get(sec, []), peg_sector.get(sec, []), cfg.comparison_confidence_global),
        ):
            bench, n = _median_without(pe_pool, c.key)
            if bench and n >= cfg.peer_min_group:
                votes = [_discount_vote((bench - c.pe) / bench, cfg)]
                own_peg = peg(c, cfg)
                if own_peg is not None:
                    pbench, pn = _median_without(peg_pool, c.key)
                    if pbench and pn >= cfg.peer_min_group:
                        votes.append(_discount_vote((pbench - own_peg) / pbench, cfg))
                chosen = (sum(votes) / len(votes), conf, scope)
                break
        if chosen:
            out[c.key] = chosen
        elif raw_ok:
            out[c.key] = (raw[0], raw[1], "small_group")
        else:
            out[c.key] = (None, 0.0, "none")
    return out


# ---------------------------------------------------------------------------------- (a) score / confidence
def known_score(
    signals: Mapping[str, Tuple[float, float]], cfg: InvestmentConfig = DEFAULT_CONFIG
) -> Tuple[float, float, int, Dict[str, float]]:
    """(score, mean confidence, agents with data, votes used) over agents that have data only."""
    used: Dict[str, float] = {}
    weighted = conf_total = 0.0
    for agent, (vote, confidence) in signals.items():
        if not has_data((vote, confidence), cfg):
            continue
        conf = _clamp(float(confidence), 0.0, 1.0)
        v = _clamp(float(vote))
        used[agent] = v
        weighted += v * conf
        conf_total += conf
    n = len(used)
    if n == 0 or conf_total <= 0:
        return 0.0, 0.0, 0, used
    return weighted / conf_total, conf_total / n, n, used


def has_disagreement(signals: Mapping[str, Tuple[float, float]], cfg: InvestmentConfig = DEFAULT_CONFIG) -> bool:
    """A confident agent at >= +0.35 against another confident one at <= -0.35 (votes as used in this mode)."""
    pos = any(c >= cfg.disagree_confidence and v >= cfg.disagree_positive for v, c in signals.values())
    neg = any(c >= cfg.disagree_confidence and v <= cfg.disagree_negative for v, c in signals.values())
    return pos and neg


def reasons(used: Mapping[str, float], conf: Mapping[str, float]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Top 2 positive and top 2 negative agents ranked by vote x confidence."""
    contrib = {a: v * conf[a] for a, v in used.items()}
    pos = sorted((a for a in used if contrib[a] > 0), key=lambda a: -contrib[a])[:2]
    neg = sorted((a for a in used if contrib[a] < 0), key=lambda a: contrib[a])[:2]
    return tuple(f"{a} ({used[a]:+.2f})" for a in pos), tuple(f"{a} ({used[a]:+.2f})" for a in neg)


LOW_COVERAGE_CONFIDENCE_FACTOR = 0.85


def low_statement_coverage(coverage: Optional[float]) -> bool:
    """Evidence coverage under the conservative ranking minimum (``BIAP_GLOBAL_RANK_MIN_COVERAGE_PCT``, default 60)."""
    if coverage is None:
        return False
    try:
        minimum = float(os.environ.get("BIAP_GLOBAL_RANK_MIN_COVERAGE_PCT", "60"))
    except ValueError:
        minimum = 60.0
    return coverage * 100.0 < max(0.0, min(100.0, minimum))


def _blocked(key: str, why: str, n: int = 0, scope: str = "none", flags: Tuple[str, ...] = ()) -> InvestmentDecision:
    return InvestmentDecision(
        key=key, call=NO_REC, score=None, confidence=None, agents_with_data=n, rank=None, percentile=None,
        position_size_hint=None, flags=flags + ("hard_block",), peer_scope=scope,
        reason=f"blocked: {why}", blocked_by=why,
    )


def _tier(rank_index: int, total: int, score: float, cfg: InvestmentConfig, n_agents: int = 6) -> str:
    """Relative tier by position in the market, gated by the score sign and (BUY / SELL) the agents with data."""
    if total <= 0:
        return "HOLD"
    pos = (rank_index + 1) / total                       # 0 < pos <= 1, small = best
    if pos <= cfg.buy_top_fraction and score > cfg.buy_min_score and n_agents >= cfg.buy_min_agents:
        return "BUY"
    if pos <= cfg.accumulate_top_fraction and score > cfg.accumulate_min_score:
        return "ACCUMULATE"
    inv = (total - rank_index) / total                   # small = worst
    if inv <= cfg.sell_bottom_fraction and score < cfg.sell_max_score and n_agents >= cfg.sell_min_agents:
        return "SELL"
    if inv <= cfg.reduce_bottom_fraction and score < cfg.reduce_max_score:
        return "REDUCE"
    return "HOLD"


def _collapse_listings(candidates: Sequence[Candidate], cfg: InvestmentConfig):
    """One candidate per (market, ISIN) for grouped venues (Xetra + Frankfurt = ``DE``); returns (batch, dup map).

    The listing with the most agents with data (then the highest summed confidence, then key) represents the
    issuer; its decision is copied to the other listings (flag ``duplicate_listing``).
    """
    groups: Dict[Tuple[str, str], List[Candidate]] = {}
    batch: List[Candidate] = []
    for c in candidates:
        if c.exchange in MARKET_GROUPS and c.isin:
            groups.setdefault((MARKET_GROUPS[c.exchange], c.isin), []).append(c)
        else:
            batch.append(c)
    dups: Dict[str, List[str]] = {}
    for (market, _), members in groups.items():
        members.sort(key=lambda m: (-sum(1 for v in m.signals.values() if has_data(v, cfg)),
                                    -sum(v[1] for v in m.signals.values()), m.key))
        batch.append(replace(members[0], exchange=market))
        if len(members) > 1:
            dups[members[0].key] = [m.key for m in members[1:]]
    return batch, dups


def decide_market(
    candidates: Sequence[Candidate], cfg: InvestmentConfig = DEFAULT_CONFIG
) -> Dict[str, InvestmentDecision]:
    """Investment-mode decisions for a batch (any number of exchanges); ranking is done per market.

    Xetra and Frankfurt are one market (``MARKET_GROUPS``), deduplicated by ISIN before ranking and tiering.
    Hand over every covered market in one batch to enable the cross-market ``global_sector`` peer scope.
    Exchanges outside ``INVESTMENT_MODE_MARKETS`` are hidden (no decision, not in any peer pool) unless the scope
    switch is ``all``.
    """
    if cfg.restrict_to_markets and scope_restricted():
        candidates = [c for c in candidates if in_scope(c.exchange, True)]       # hidden markets take no part
    batch, dups = _collapse_listings(candidates, cfg)
    decisions = _decide_core(batch, cfg)
    for rep_key, others in dups.items():
        if rep_key in decisions:
            for key in others:
                d = decisions[rep_key]
                decisions[key] = replace(d, key=key, flags=d.flags + ("duplicate_listing",))
    return decisions


def _decide_core(
    candidates: Sequence[Candidate], cfg: InvestmentConfig = DEFAULT_CONFIG
) -> Dict[str, InvestmentDecision]:
    risk_votes = relative_risk_votes(candidates, cfg)
    comp = comparison_votes(candidates, cfg)
    decisions: Dict[str, InvestmentDecision] = {}
    detail: Dict[str, tuple] = {}
    per_exchange: Dict[str, List[str]] = {}

    for c in candidates:
        scope = comp[c.key][2]
        if c.evidence_status == "BLOCK":
            decisions[c.key] = _blocked(c.key, "evidence BLOCK", scope=scope)
            continue
        signals: Dict[str, Tuple[float, float]] = dict(c.signals)
        if c.key in risk_votes:
            signals["risk"] = (risk_votes[c.key], signals["risk"][1])
        elif "risk" in signals:
            signals["risk"] = (0.0, 0.0)
        vote, cconf, _ = comp[c.key]
        if vote is None:
            signals["comparison"] = (0.0, 0.0)
        else:
            signals["comparison"] = (vote, cconf)
        score, mean_conf, n, used = known_score(signals, cfg)
        if n < cfg.min_agents_hard_block:
            decisions[c.key] = _blocked(
                c.key, f"only {n} agent(s) with data (need {cfg.min_agents_hard_block})", n, scope)
            continue
        confidence = mean_conf * _clamp(c.evidence_multiplier, 0.0, 1.0)
        if low_statement_coverage(c.statement_coverage):
            confidence *= LOW_COVERAGE_CONFIDENCE_FACTOR     # the conservative 60% rule is a flag here, not a block
        if n < cfg.min_agents_full_confidence:
            confidence *= n / cfg.min_agents_full_confidence
        detail[c.key] = (c, signals, score, confidence, n, used, scope)
        per_exchange.setdefault(c.exchange, []).append(c.key)

    for keys in per_exchange.values():
        ordered = sorted(keys, key=lambda k: (-detail[k][2], -detail[k][3], k))
        total = len(ordered)
        for idx, key in enumerate(ordered):
            c, signals, score, confidence, n, used, scope = detail[key]
            tier = _tier(idx, total, score, cfg, n)
            base_tier = tier
            flags: List[str] = []
            if has_disagreement(signals, cfg):
                flags.append("agents_disagree")
            if n < cfg.min_agents_full_confidence:
                flags.append("few_agents")
            if scope in ("exchange_sector", "global_sector"):
                flags.append(f"peer_scope_{scope}")
            if scope in ("small_group", "book_value", "none"):
                flags.append("peer_group_small" if scope == "small_group" else "no_peer_comparison")
            if c.distress_status in cfg.distress_unknown:
                flags.append("distress_unknown")
            elif c.distress_status not in cfg.buy_distress_ok:
                flags.append("distress_not_low_risk")
            if not any(a != "comparison" and v > 0 for a, v in used.items()):
                flags.append("no_independent_signal")
            if c.evidence_status == "WARN":
                flags.append("evidence_warn")
            if low_statement_coverage(c.statement_coverage):
                flags.append("statement_coverage_below_min")
            if (cfg.widened_guard and base_tier == "BUY" and scope in ("exchange_sector", "global_sector")
                    and not any(a != "comparison" and signals[a][0] >= cfg.widened_guard_vote
                                and signals[a][1] >= cfg.widened_guard_confidence for a in used)):
                flags.append("widened_peers")
            soft = [f for f in flags if f in cfg.soft_downgrade_flags]
            if tier == "SELL" and "agents_disagree" in flags:
                tier = "REDUCE"
            elif tier == "BUY" and soft:
                tier = "ACCUMULATE"
            if c.positive_block and tier in ("BUY", "ACCUMULATE"):
                decisions[key] = _blocked(key, "distress positive_block", n, scope, tuple(flags))
                continue
            pos, neg = reasons(used, {a: signals[a][1] for a in used})
            decisions[key] = InvestmentDecision(
                key=key, call=tier, score=round(score, 6), confidence=round(confidence, 6), agents_with_data=n,
                rank=idx + 1, percentile=round(idx / total, 6),
                position_size_hint=position_size_hint(confidence, cfg), flags=tuple(flags), peer_scope=scope,
                positive_reasons=pos, negative_reasons=neg,
                reason=f"+ {', '.join(pos) or 'none'} | - {', '.join(neg) or 'none'}",
                tier_before_flags=base_tier if base_tier != tier else None, used_votes=dict(used),
            )
    return decisions


def apply_decision_mode(
    candidates: Iterable[Candidate], mode: Optional[str] = None, cfg: Optional[InvestmentConfig] = None
) -> Dict[str, InvestmentDecision]:
    """Investment decisions when the mode is ``investment``, else ``{}`` (callers keep the conservative call)."""
    if decision_mode(mode) != INVESTMENT:
        return {}
    return decide_market(list(candidates), cfg or load_config())


# ---------------------------------------------------------------------------------- stored results
def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def earnings_growth_pct(company: Mapping[str, Any]) -> Optional[float]:
    """Net-income growth if both years are positive, else revenue growth (None if neither is known)."""
    ni, rev_prev, margin_prev = _num(company.get("net_income")), _num(company.get("revenue_prev")), \
        _num(company.get("net_margin_prev_pct"))
    if ni and ni > 0 and rev_prev and margin_prev and margin_prev > 0:
        prev = rev_prev * margin_prev / 100.0
        if prev > 0:
            return (ni / prev - 1.0) * 100.0
    return _num(company.get("revenue_yoy_pct"))


def _native_peer_count(company: Mapping[str, Any]) -> Optional[int]:
    raw = company.get("raw_provider_fields") or {}
    n = raw.get("peer_pe_benchmark_count")
    if raw.get("peer_pe_benchmark_scope") == "same_sector_scan_median" and isinstance(n, int) and not isinstance(n, bool):
        return n
    return None


def candidate_from_result(result: Mapping[str, Any], *, key: Optional[str] = None, sector_override: Optional[str] = None
                          ) -> Optional[Candidate]:
    """Build a Candidate from a stored full analysis result (``AnalysisLedger.full_results`` row)."""
    signals = {
        s["agent"]: (float(s["vote"]), float(s.get("confidence") or 0.0))
        for s in result.get("signals") or () if s.get("agent") is not None and s.get("vote") is not None
    }
    if not signals:
        return None
    company = result.get("company") or {}
    ev = result.get("evidence") or {}
    dist = result.get("distress") or {}
    exchange = str(result.get("exchange") or company.get("exchange") or "")
    country = str(result.get("country") or company.get("country") or "")
    if country and ":" not in exchange:
        exchange = f"{country}:{exchange}"                 # same CC:EXCHANGE form as MARKET_GROUPS / the scope list
    ticker = str(result.get("ticker") or company.get("ticker") or "")
    mult = _num(ev.get("confidence_multiplier"))
    return Candidate(
        statement_coverage=_num(ev.get("coverage")),
        key=key or f"{exchange}:{ticker}", exchange=exchange,
        sector=sector_override or company.get("sector") or None, signals=signals,
        evidence_status=str(ev.get("status") or "PASS"),
        evidence_multiplier=1.0 if mult is None else mult,
        positive_block=bool(dist.get("positive_block")), distress_status=dist.get("status"),
        isin=result.get("isin") or company.get("isin"), pe=_num(company.get("pe")),
        growth_pct=earnings_growth_pct(company), peer_count=_native_peer_count(company),
        risk_metrics={
            "volatility_pct": _num(company.get("volatility_annualized_pct")),
            "drawdown_pct": _num(company.get("max_drawdown_pct")),
            "liabilities": _num(company.get("total_liabilities")), "equity": _num(company.get("total_equity")),
            "debt": _num(company.get("total_debt")), "operating_cash_flow": _num(company.get("operating_cash_flow")),
            "current_ratio": (
                _num(company.get("current_assets")) / _num(company.get("current_liabilities"))
                if _num(company.get("current_assets")) is not None and _num(company.get("current_liabilities"))
                else None),
        },
    )


def decide_ledger(ledger: Any, cfg: Optional[InvestmentConfig] = None) -> Dict[str, InvestmentDecision]:
    """Read-only: investment decisions for one ``AnalysisLedger`` (its stored results, own exchange only)."""
    cands = [c for c in (candidate_from_result(r) for r in ledger.full_results()) if c is not None]
    return decide_market(cands, cfg or load_config())
