"""Shared loader for the research-paper scripts: reads ONLY the frozen snapshot and replays both decision modes.

    snapshot (read-only ledgers)  ->  rows (investment candidate + conservative gate row)
                                  ->  conservative replay (audit_decision_rule.decide) and investment replay (decide_market)

Nothing here touches /var/lib/biap-global; the snapshot manifest is verified before any ledger is opened.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from global_markets import investment_mode as im  # noqa: E402
import audit_decision_rule as A  # noqa: E402
import investment_mode_replay as R  # noqa: E402

DEFAULT_SNAPSHOT = Path("~/biap_research/snapshot_2026-10-19").expanduser()
DEFAULT_TMP = Path("~/biap_research/tmp").expanduser()
AGENTS = im.AGENTS
CONS_TIERS = ("BUY", "HOLD", "SELL", "NO_RECOMMENDATION")
INV_TIERS = ("BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL", "NO_RECOMMENDATION")
CONS_FROM_STORED = {"BUY_CANDIDATE": "BUY", "HOLD_OR_WATCH": "HOLD", "AVOID_OR_REVIEW": "SELL", "NO_RECOMMENDATION": "NO_RECOMMENDATION"}

# Conservative gate cascade, in the order the paper reports it. Each stock is attributed to the FIRST group it fails.
# The PR #52 BUY rules (distress not LOW_RISK, peers >= 8, independent signal, comparison evidence) are included
# because they are the conservative BUY rule under review; the stored calls pre-date them (see Params in the audit).
CASCADE = (
    ("score", ("SCORE_BELOW_0.25",)),
    ("confidence", ("CONFIDENCE_BELOW_0.35", "CONFIDENCE_BELOW_0.45", "CONFIDENCE_BELOW_0.55")),
    ("evidence", ("EVIDENCE_BLOCK", "EVIDENCE_WARN")),
    ("disagreement", ("AGENT_DISAGREEMENT",)),
    ("distress", ("DISTRESS_POSITIVE_BLOCK", "DISTRESS_NOT_LOW_RISK")),
    ("peers", ("PEER_GROUP_BELOW_8",)),
    ("independent_signal", ("NO_INDEPENDENT_POSITIVE_SIGNAL",)),
    ("comparison_evidence", ("COMPARISON_EVIDENCE_GAP",)),
)
GATE_PARAMS = A.Params("conservative + PR52 BUY rules", buy_rules=frozenset(A.BUY_ONLY_GATES - {"DISTRESS_POSITIVE_BLOCK"}))


def market_of(exchange: str) -> str:
    """Counting market: DE:XETRA and DE:FRANKFURT are one market ``DE``."""
    return im.MARKET_GROUPS.get(exchange, exchange)


def country_of(exchange: str) -> str:
    return exchange.split(":", 1)[0]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_snapshot(snap: Path) -> dict:
    """Raise SystemExit when any snapshot file differs from MANIFEST.sha256.json."""
    manifest = json.loads((snap / "MANIFEST.sha256.json").read_text())
    for rel, meta in manifest["files"].items():
        if sha256(snap / rel) != meta["sha256"]:
            raise SystemExit(f"snapshot file changed since the freeze: {rel}")
    return manifest


def gate_group(failed: list[str]) -> str:
    """First cascade group the failed gates fall into, else PASS."""
    for name, gates in CASCADE:
        if any(g in failed for g in gates):
            return name
    return "PASS"


def _gate_row(row: R.Row, d: dict) -> A.Row:
    g = A.Row(country=row.country, exchange=row.exchange, ticker=row.ticker, name=row.name, ledger_status=row.status,
              reason=row.reason, stored_call=row.stored_call, score=None, confidence=None, liquidity_value=row.liquidity,
              price=row.price, quote_date=row.quote_date, currency=row.currency, isin=row.isin,
              analyzed_at=row.analyzed_at, signals={})
    A._fill_from_result(g, d)
    return g


def load(snap: Path, tmp: Path, cfg: im.InvestmentConfig | None = None, *, check: bool = True):
    """-> (rows, decisions, counted) with both modes replayed on the frozen snapshot.

    ``counted`` = keys of the analysed rows that represent an issuer (the duplicate Xetra/Frankfurt listing is left out).
    """
    snap = Path(snap).expanduser()
    if check:
        verify_snapshot(snap)
    ref = json.loads((snap / "reference" / "sector_reference_entries.json").read_text()).get("entries", {})
    tmp = Path(tmp).expanduser() / "research-load"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        rows = R.load_all(snap / "ledgers", tmp, ref, on_result=lambda row, d: setattr(row, "gate", _gate_row(row, d)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cfg = cfg or im.load_config("")
    decisions = R.replay(rows, cfg)
    counted = {r.key for r in rows if r.analysed and r.key in decisions and "duplicate_listing" not in decisions[r.key].flags}
    return rows, decisions, counted


def conservative_tier(row: R.Row) -> str:
    """Replay of the conservative engine (service._call + Agent 8 governance) from the stored signals."""
    return CONS_FROM_STORED[A.decide(row.gate, A.Params())]


def tier_counts(rows, decisions, counted, level: str = "market") -> dict:
    """{unit: {"conservative": {tier: n}, "investment": {tier: n}, "analysed": n}}; ``level`` = market | country."""
    unit = (lambda ex: market_of(ex)) if level == "market" else (lambda ex: country_of(ex))
    out: dict = {}
    for r in rows:
        if not r.analysed or r.key not in counted:
            continue
        u = out.setdefault(unit(r.exchange), {"analysed": 0, "conservative": Counter(), "investment": Counter()})
        u["analysed"] += 1
        u["conservative"][conservative_tier(r)] += 1
        u["investment"][decisions[r.key].call] += 1
    return {k: {"analysed": v["analysed"],
                "conservative": {t: v["conservative"][t] for t in CONS_TIERS},
                "investment": {t: v["investment"][t] for t in INV_TIERS}} for k, v in sorted(out.items())}


def replay_mismatches(rows) -> list:
    """Analysed rows whose conservative replay differs from the stored call (the replay is expected to be exact)."""
    return [(r.key, r.stored_call, A.decide(r.gate, A.Params())) for r in rows
            if r.analysed and r.gate is not None and A.decide(r.gate, A.Params()) != r.stored_call]
