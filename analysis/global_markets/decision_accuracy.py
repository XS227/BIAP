"""Decision Accuracy Agent (advisory, OFF by default): BIAP's own track record.

Realised returns of BUY / SELL decisions against each market's benchmark, per market, side and horizon (1, 3, 6, 12 months), with hit rate,
BUY-SELL spread and bootstrap intervals, and a per-stock view. Read-only: it only reads versioned cohort files in
``data/decision_accuracy/`` (the first is built from the FROZEN v1 paper cohort by ``tools/decision_accuracy_import_v1.py``); it never
writes any file, ledger or decision, and a horizon that has not matured is reported as PENDING, never extrapolated.
Plan: docs/agents/decision_accuracy_agent_plan.md. Flag ``DECISION_ACCURACY_AGENT_ENABLED`` (default off -> routes answer 404).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

FLAG = "DECISION_ACCURACY_AGENT_ENABLED"
VERSION = 1
DATA_DIR = Path(__file__).resolve().parent / "data" / "decision_accuracy"
DATA_DIR_ENV = "DECISION_ACCURACY_DATA_DIR"


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV) or DATA_DIR)


def load_config() -> dict:
    cfg = json.loads((_dir() / "config.json").read_text(encoding="utf-8"))
    for key in ("horizons_months", "min_priced_per_side", "bootstrap_resamples", "bootstrap_seed", "confidence_level", "cohorts"):
        if key not in cfg:
            raise ValueError(f"decision accuracy config is missing {key}")
    return cfg


def _canonical_sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def load_cohort(cohort_id: str) -> dict:
    """Read one cohort file (read-only) and verify its content hash; a tampered file is rejected."""
    path = _dir() / f"{cohort_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    stored = data.get("contentSha256")
    body = {k: v for k, v in data.items() if k != "contentSha256"}
    if stored != _canonical_sha(body):
        raise ValueError(f"cohort {cohort_id}: content hash mismatch (file altered or corrupt)")
    return data


# --- pure maths ---------------------------------------------------------------------------------------------------------------
def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, last))


def matures_on(decision_date: str, horizon_months: int) -> date:
    return add_months(date.fromisoformat(decision_date), int(horizon_months))


def excess_return(ret: float, bench: float) -> float:
    return ret - bench


def is_hit(side: str, ret: float, bench: float) -> bool:
    """BUY hits when it beats its benchmark, SELL hits when it trails it."""
    return ret > bench if side == "BUY" else ret < bench


def wilson(k: int, n: int, z: float = 1.959964) -> Optional[tuple]:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    return statistics.median(xs) if xs else None


def bootstrap_spread(rows: list, *, resamples: int, seed: int, level: float, venue_equal: bool = False) -> Optional[tuple]:
    """CI of mean(BUY) - mean(SELL) resampling holdings with replacement within market x side. rows: (market, side, return).
    venue_equal=True: each side's figure is the mean of the per-market means (every venue weighs the same), as in the paper."""
    strata: dict = {}
    for m, side, r in rows:
        strata.setdefault((m, side), []).append(r)
    if not any(k[1] == "BUY" for k in strata) or not any(k[1] == "SELL" for k in strata):
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        buy, sell = [], []
        for (m, side), xs in strata.items():
            draw = rng.choices(xs, k=len(xs))
            if venue_equal:
                (buy if side == "BUY" else sell).append(sum(draw) / len(draw))
            else:
                (buy if side == "BUY" else sell).extend(draw)
        out.append(sum(buy) / len(buy) - sum(sell) / len(sell))
    out.sort()
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return out[int(lo * (resamples - 1))], out[int(hi * (resamples - 1))]


# --- aggregation --------------------------------------------------------------------------------------------------------------
def _horizon_state(cohort: Mapping, horizon: int, today: Optional[date]) -> dict:
    due = matures_on(cohort["decisionDate"], horizon)
    present = any(str(horizon) in d.get("outcomes", {}) for d in cohort["decisions"]) and str(horizon) in cohort.get("benchmarks", {})
    if present:
        return {"status": "MATURED", "matures": due.isoformat(), "note": (cohort.get("horizonNotes") or {}).get(str(horizon))}
    state = "PENDING" if (today or date.today()) < due else "NOT_COMPUTED"
    return {"status": state, "matures": due.isoformat(), "note": None}


def _records(cohort: Mapping, horizon: int, market: Optional[str] = None) -> list:
    bench = (cohort.get("benchmarks") or {}).get(str(horizon), {})
    recs = []
    for d in cohort["decisions"]:
        o = (d.get("outcomes") or {}).get(str(horizon))
        if not o or o.get("status") != "PRICED" or d["market"] not in bench or (market and d["market"] != market):
            continue
        b = bench[d["market"]]["returnPct"] / 100.0
        recs.append({**d, "ret": o["return"], "bench": b, "excess": excess_return(o["return"], b), "hit": is_hit(d["side"], o["return"], b),
                     "exitDate": o.get("exitDate")})
    return recs


def _side_stats(recs: list, side: str) -> dict:
    xs = [r for r in recs if r["side"] == side]
    n = len(xs)
    hits = sum(1 for r in xs if r["hit"])
    ci = wilson(hits, n)
    return {"n": n, "meanReturnPct": _pct(_mean([r["ret"] for r in xs])), "medianReturnPct": _pct(_median([r["ret"] for r in xs])),
            "meanExcessPct": _pct(_mean([r["excess"] for r in xs])), "hitRate": None if not n else hits / n,
            "hitRateCi95": None if ci is None else [ci[0], ci[1]]}


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else x * 100.0


POSITIVE_RANKING_WORDING = ("positive BUY-SELL ranking spread over one month; absolute returns were negative in a falling market; "
                            "longer horizons pending")


def _venue_equal(recs: list, rows: list, cfg: Mapping) -> dict:
    """PRIMARY pooled figure: every market (venue) counts once per side, as in the paper (BUY -0.35%, SELL -10.93%, spread 10.57 pp)."""
    per = {}
    for m in sorted({r["market"] for r in recs}):
        mr = [r for r in recs if r["market"] == m]
        per[m] = {side: [x for x in mr if x["side"] == side] for side in ("BUY", "SELL")}
    out = {"weighting": "venue-equal (mean of the per-venue means; primary, matches the paper)"}
    for side in ("BUY", "SELL"):
        ms = [(_mean([x["ret"] for x in v[side]]), _mean([x["excess"] for x in v[side]]),
               sum(1 for x in v[side] if x["hit"]) / len(v[side])) for v in per.values() if v[side]]
        out[side.lower()] = {"venues": len(ms), "n": sum(len(v[side]) for v in per.values()),
                             "meanReturnPct": _pct(_mean([a for a, _, _ in ms])) if ms else None,
                             "meanExcessPct": _pct(_mean([b for _, b, _ in ms])) if ms else None,
                             "hitRate": _mean([c for _, _, c in ms]) if ms else None}
    b, s_ = out["buy"], out["sell"]
    out["spreadMeanPp"] = None if b["meanReturnPct"] is None or s_["meanReturnPct"] is None else b["meanReturnPct"] - s_["meanReturnPct"]
    out["excessSpreadMeanPp"] = None if b["meanExcessPct"] is None or s_["meanExcessPct"] is None else b["meanExcessPct"] - s_["meanExcessPct"]
    ci = bootstrap_spread(rows, resamples=int(cfg["bootstrap_resamples"]), seed=int(cfg["bootstrap_seed"]),
                          level=float(cfg["confidence_level"]), venue_equal=True)
    out["spreadCi95Pp"] = None if ci is None else [ci[0] * 100.0, ci[1] * 100.0]
    out["note"] = "venues are not independent (two US venues, two German venues); the interval resamples holdings within venue and side"
    return out


def _stock_weighted(recs: list, rows: list, cfg: Mapping) -> dict:
    """SECONDARY pooled figure: every priced holding counts once, so large venues (US) dominate."""
    buy, sell = _side_stats(recs, "BUY"), _side_stats(recs, "SELL")
    ci = bootstrap_spread(rows, resamples=int(cfg["bootstrap_resamples"]), seed=int(cfg["bootstrap_seed"]), level=float(cfg["confidence_level"]))
    return {"weighting": "stock-weighted (all priced holdings pooled; secondary, dominated by the largest venues)", "buy": buy, "sell": sell,
            "spreadMeanPp": None if buy["meanReturnPct"] is None or sell["meanReturnPct"] is None else buy["meanReturnPct"] - sell["meanReturnPct"],
            "spreadCi95Pp": None if ci is None else [ci[0] * 100.0, ci[1] * 100.0],
            "excessSpreadMeanPp": None if buy["meanExcessPct"] is None or sell["meanExcessPct"] is None else buy["meanExcessPct"] - sell["meanExcessPct"]}


def summarize(cohort: Mapping, horizon: int, *, market: Optional[str] = None, config: Optional[Mapping] = None, today: Optional[date] = None) -> dict:
    cfg = config or load_config()
    state = _horizon_state(cohort, horizon, today)
    base = {"cohortId": cohort["cohortId"], "decisionDate": cohort["decisionDate"], "decisionLogicVersion": cohort.get("decisionLogicVersion"),
            "horizonMonths": horizon, "horizon": state, "returnBasis": cohort.get("returnBasis")}
    if state["status"] != "MATURED":
        return {**base, "markets": None, "pooled": None,
                "message": f"{horizon}-month horizon not matured: due {state['matures']}" if state["status"] == "PENDING" else "outcomes not computed yet"}
    recs = _records(cohort, horizon, market)
    markets = {}
    for m in sorted({r["market"] for r in recs}):
        mr = [r for r in recs if r["market"] == m]
        buy, sell = _side_stats(mr, "BUY"), _side_stats(mr, "SELL")
        small = min(buy["n"], sell["n"]) < int(cfg["min_priced_per_side"])
        spread = None if buy["meanReturnPct"] is None or sell["meanReturnPct"] is None else buy["meanReturnPct"] - sell["meanReturnPct"]
        mspread = None if buy["medianReturnPct"] is None or sell["medianReturnPct"] is None else buy["medianReturnPct"] - sell["medianReturnPct"]
        markets[m] = {"benchmark": cohort["benchmarks"][str(horizon)][m], "buy": buy, "sell": sell, "spreadMeanPp": spread, "spreadMedianPp": mspread,
                      "tooSmallToInterpret": small}
    pooled = pooled_sw = None
    if recs:
        rows = [(r["market"], r["side"], r["ret"]) for r in recs]
        pooled = _venue_equal(recs, rows, cfg)
        pooled_sw = _stock_weighted(recs, rows, cfg)
    return {**base, "markets": markets, "pooled": pooled, "pooledStockWeighted": pooled_sw,
            "caveats": ["past decisions, not a forecast", POSITIVE_RANKING_WORDING,
                        "markets and venues are not independent observations", "price returns only (no dividends)"]}


def stock_record(cohorts: list, country: str, exchange: str, ticker: str, *, config: Optional[Mapping] = None, today: Optional[date] = None) -> dict:
    cfg = config or load_config()
    items = []
    for c in cohorts:
        for d in c["decisions"]:
            if d["country"].upper() == country.upper() and d["exchange"].upper() == exchange.upper() and d["ticker"].upper() == ticker.upper():
                horizons = {}
                for h in cfg["horizons_months"]:
                    st = _horizon_state(c, h, today)
                    rec = next((r for r in _records(c, h) if r["market"] == d["market"] and r["ticker"] == d["ticker"] and r["side"] == d["side"]), None) \
                        if st["status"] == "MATURED" else None
                    if rec:
                        horizons[str(h)] = {"status": "MATURED", "returnPct": rec["ret"] * 100, "benchmarkPct": rec["bench"] * 100,
                                            "excessPct": rec["excess"] * 100, "hit": rec["hit"], "exitDate": rec["exitDate"]}
                    elif st["status"] == "MATURED":
                        o = (d.get("outcomes") or {}).get(str(h)) or {}
                        horizons[str(h)] = {"status": "NOT_PRICED", "reason": o.get("reason")}
                    else:
                        horizons[str(h)] = {"status": st["status"], "matures": st["matures"]}
                items.append({"cohortId": c["cohortId"], "decisionDate": c["decisionDate"], "decisionLogicVersion": c.get("decisionLogicVersion"),
                              "side": d["side"], "tier": d["tier"], "score": d.get("score"), "entryClose": d.get("entryClose"), "horizons": horizons})
    return {"agent": "decision_accuracy", "version": VERSION, "advisoryOnly": True, "country": country, "exchange": exchange, "ticker": ticker,
            "decisions": items, "n": len(items),
            "note": "one cohort gives one observation per stock: this is an anecdote, not a track record, until more cohorts mature"}


def load_all() -> list:
    return [load_cohort(c) for c in load_config()["cohorts"]]
