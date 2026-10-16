"""Source-aware freshness model for peer benchmarks (all countries).

The old model used ONE wall-clock number (cachedAt <= 24 h) for everything, so a
benchmark whose inputs had not changed expired every day and every market needed a
re-scan. Here validity is split into independent dimensions, and only quotes and
risk signals are time-based:

* filing validity    - peer fundamentals are valid until a newer filing can have been
                       PUBLISHED since the base was built (country reporting calendar), or
                       a source update names a newer period. Not a TTL.
* peer-universe      - valid while the (ticker, ISIN) set equals the validated one.
* benchmark calc     - a pure function of (universe fp, fundamentals fp, quote date,
                       METHOD_VERSION); valid iff the stored calc fingerprint still
                       equals the recomputed one. Edited rows / new code => invalid.
* quote freshness    - exchange quote date within a calendar-day tolerance; renewed by
                       an in-memory online read (reprice), never by relabelling.
* risk-signal        - price-history risk inputs (volatility, drawdown) of the TARGET.

Validity models (what expires and what never does):

* immutable historical evidence - a filing for period P (fundamentals archive, ESEF package, ledger
                       row) never expires. It can only become SUPERSEDED when a newer period is known;
                       a superseded report stays stored and readable, it is just not "current".
* peer benchmark input version - fingerprints of the stored evidence a benchmark was computed from.
* current quote       - only an exchange quote dated within tolerance is CURRENT; an older price is
                       HISTORICAL and is never relabelled current (rows without a current quote are
                       excluded from a benchmark, not repriced from old prices).
* decision freshness  - derived from the above; BUY needs every critical component valid.

Anything that cannot be established (no period end, fingerprint mismatch, unknown
version) is UNDETERMINED/STALE and the caller fails closed (no peer benchmark => a
BUY cannot be accepted). Nothing here extends a timestamp.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

METHOD_VERSION = 2           # bump when benchmark maths / required inputs change => all benchmarks recompute
BLOCK_SCHEMA = 2
VALID, STALE, UNDETERMINED = "VALID", "STALE", "UNDETERMINED"
MAX_EXCLUDED_PCT = 15.0      # peers that may be excluded (possibly superseded / undated / unrepriceable) before the benchmark is not trusted
QUOTE_TOLERANCE_DAYS = 4     # weekend + one holiday; env BIAP_GLOBAL_PEER_QUOTE_TOLERANCE_DAYS
RISK_SIGNAL_MAX_AGE_DAYS = 5
DEFAULT_BASE_CEILING_HOURS = 336.0  # backstop until a source-update feed exists (env BIAP_GLOBAL_PEER_BASE_MAX_HOURS)

# (cadence_days, filing_lag_days, min_lag_days) per reporting regime; owner-tunable policy, see docs.
_QUARTERLY = (92, 45, 20)    # (cadence, deadline lag, earliest realistic publication lag)
_SEMIANNUAL = (183, 75, 40)
FILING_CADENCE = {c: _QUARTERLY for c in ("US", "CA", "JP", "KR", "IN", "SE", "NO", "FI", "SA", "TR", "BR", "ZA", "SG")}
DEFAULT_CADENCE = _SEMIANNUAL  # conservative: unknown countries get the longer interval


def _h(parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:16]


def _co(row) -> dict:
    co = row.get("company") if isinstance(row, dict) else None
    return co if isinstance(co, dict) else {}


def universe_fingerprint(rows: list) -> str:
    return _h(sorted((str(_co(r).get("ticker") or "").upper(), str(_co(r).get("isin") or "")) for r in rows))


def fundamentals_fingerprint(rows: list) -> str:
    """Price-independent inputs only, so repricing never changes it but a re-extracted filing does."""
    keys = ("sector", "filing_period_end", "eps", "ebitda", "net_income", "revenue", "total_debt")
    return _h(sorted((str(_co(r).get("ticker") or "").upper(), r.get("inputsAsOf") if isinstance(r, dict) else None,
                      *[_co(r).get(k) for k in keys]) for r in rows))


def calc_fingerprint(universe_fp: str, fundamentals_fp: str, quotes_as_of: Optional[str]) -> str:
    return _h([universe_fp, fundamentals_fp, quotes_as_of, METHOD_VERSION])


def _date(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def quote_tolerance_days() -> int:
    try:
        return max(1, int(os.environ.get("BIAP_GLOBAL_PEER_QUOTE_TOLERANCE_DAYS", QUOTE_TOLERANCE_DAYS)))
    except ValueError:
        return QUOTE_TOLERANCE_DAYS


def base_ceiling_hours() -> float:
    try:
        return max(1.0, float(os.environ.get("BIAP_GLOBAL_PEER_BASE_MAX_HOURS", DEFAULT_BASE_CEILING_HOURS)))
    except ValueError:
        return DEFAULT_BASE_CEILING_HOURS


LAG_SLACK_DAYS = 15


def per_row_evidence_age(rows: list) -> bool:
    """True when every row records when its evidence was produced; then the age ceiling applies per row."""
    return bool(rows) and all(isinstance(r, dict) and _date(r.get("inputsAsOf")) for r in rows)


def filing_may_have_changed(country: str, period_end: date, base: date, today: date) -> bool:
    """Could a filing newer than ``period_end`` have been PUBLISHED after the base scan was built?

    Walks the country's reporting calendar (period_end + k*cadence) and checks whether any
    publication window [period+min_lag, period+lag+slack] (regime table above) overlaps (base, today]. Filings
    published before the base are not a change: the base already is the state the pipeline
    chose to use (annual-based peer rows stay valid until a new filing can actually appear).
    """
    cadence, lag, min_lag = FILING_CADENCE.get(country.upper(), DEFAULT_CADENCE)
    k = 1
    while True:
        nxt = period_end + timedelta(days=cadence * k)
        opens = nxt + timedelta(days=min_lag)
        if opens > today:
            return False
        if nxt + timedelta(days=lag + LAG_SLACK_DAYS) > base:
            return True
        k += 1


NON_MEMBER_REASONS = {"no_price_dependent_multiple", "base_price_missing", "no_company"}


def _non_member(co: dict) -> bool:
    """Row that never fed a benchmark median (no P/E and no P/B at base)."""
    reason = co.get("benchmark_excluded_reason")
    if reason:
        return reason in NON_MEMBER_REASONS
    pos = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0  # noqa: E731
    return not (pos(co.get("pe")) or pos(co.get("pb")))


def filing_dimension(rows: list, country: str, today: date, base: Optional[date] = None, superseded: Optional[dict] = None) -> dict:
    """Per-peer fundamentals validity since ``base``.

    A peer whose fundamentals may have been superseded (or cannot be dated) is EXCLUDED from the
    benchmark, never kept with a stale label. The benchmark stays usable while the excluded share
    (including peers excluded earlier for any reason) is within ``MAX_EXCLUDED_PCT``.
    """
    base = base or today
    superseded = {k.upper(): v for k, v in (superseded or {}).items()}
    reasons: dict[str, str] = {}
    newest = None
    members = 0
    for r in rows:
        co = _co(r)
        t = str(co.get("ticker") or "").upper()
        if _non_member(co):          # never had a price-dependent multiple: contributes to no median, nothing to validate
            continue
        members += 1
        if co.get("benchmark_excluded_reason"):
            reasons[t] = str(co["benchmark_excluded_reason"])
            continue
        pe = _date(co.get("filing_period_end"))
        if pe is None:
            reasons[t] = "filing_undated"
            continue
        newest = max(newest, pe) if newest else pe
        newer = _date(superseded.get(t))
        # Evidence age is per row when the row records when it was analysed (ledger rebuild).
        own_base = _date(r.get("inputsAsOf")) if isinstance(r, dict) else None
        row_base = own_base or base
        if own_base is not None and (today - own_base).days * 24 > base_ceiling_hours():
            reasons[t] = "inputs_older_than_ceiling"
        elif (newer and newer > pe) or filing_may_have_changed(country, pe, row_base, today):
            reasons[t] = "filing_may_have_changed"
    n = max(1, members)
    pct = 100.0 * len(reasons) / n
    undated = sum(1 for v in reasons.values() if v == "filing_undated")
    state = VALID if pct <= MAX_EXCLUDED_PCT else (UNDETERMINED if undated > len(reasons) / 2 else STALE)
    return {"state": state, "excludedPct": round(pct, 1), "excludedCount": len(reasons), "reasons": reasons,
            "undatedPct": round(100.0 * undated / n, 1), "newestPeriodEnd": newest.isoformat() if newest else None,
            "excluded": sorted(reasons),
            "reason": None if state == VALID else f"{pct:.0f}% of peers excluded (possibly superseded/undated/unvalidated) > {MAX_EXCLUDED_PCT:.0f}%"}


def stamp_block(rows: list, country: str, *, method: str, validated_at: datetime, base_cached_at: str,
                quotes_as_of: Optional[str], **extra) -> dict:
    u, f = universe_fingerprint(rows), fundamentals_fingerprint(rows)
    return {"schema": BLOCK_SCHEMA, "status": "VALIDATED", "method": method, "methodVersion": METHOD_VERSION,
            "validatedAt": validated_at.isoformat(), "baseCachedAt": base_cached_at, "quotesAsOf": quotes_as_of,
            "fingerprints": {"universe": u, "fundamentals": f, "calc": calc_fingerprint(u, f, quotes_as_of)}, **extra}


def quotes_as_of_of(rows: list) -> Optional[str]:
    dates = [d for d in (_date(_co(r).get("price_observed_at")) or _date((r.get("screening") or {}).get("quoteDate") if isinstance(r, dict) else None) for r in rows) if d]
    if not dates:
        return None
    dates.sort()
    return dates[len(dates) // 2].isoformat()   # median: one halted ticker must not make the whole set look old


def evaluate(wrapper: dict, country: str, now: datetime, superseded: Optional[dict] = None) -> dict:
    """Per-dimension verdicts for one stored peer benchmark. ``usable`` is the only fail-closed switch."""
    payload = wrapper.get("payload") if isinstance(wrapper, dict) else None
    rows = payload.get("deepResults") if isinstance(payload, dict) else None
    block = wrapper.get("benchmark") if isinstance(wrapper, dict) else None
    dims = {k: {"state": UNDETERMINED, "reason": "not evaluated"} for k in ("filing", "universe", "benchmark", "quote")}
    if not isinstance(rows, list) or not isinstance(block, dict) or block.get("schema") != BLOCK_SCHEMA:
        return {"usable": False, "dimensions": dims, "reason": "no v2 benchmark block"}
    fp = block.get("fingerprints") or {}
    u, f = universe_fingerprint(rows), fundamentals_fingerprint(rows)
    base = None
    try:
        base = datetime.fromisoformat(str(wrapper.get("cachedAt")).replace("Z", "+00:00"))
        base = base if base.tzinfo else base.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    structural = (block.get("status") == "VALIDATED" and block.get("methodVersion") == METHOD_VERSION
                  and base is not None and block.get("baseCachedAt") == wrapper.get("cachedAt"))
    dims["universe"] = {"state": VALID if fp.get("universe") == u else STALE,
                        "reason": None if fp.get("universe") == u else "peer universe differs from validated set"}
    fd = filing_dimension(rows, country, now.date(), base.date() if base else None, superseded)
    if fp.get("fundamentals") != f:
        fd = {**fd, "state": STALE, "reason": "fundamental inputs differ from validated fingerprint"}
    ceiling = base is not None and not per_row_evidence_age(rows) and (now - base).total_seconds() / 3600.0 > base_ceiling_hours()
    if ceiling:
        fd = {**fd, "state": STALE, "reason": f"base scan older than {base_ceiling_hours():.0f} h ceiling (no source-update feed)"}
    dims["filing"] = fd
    calc_ok = structural and fp.get("calc") == calc_fingerprint(fp.get("universe"), fp.get("fundamentals"), block.get("quotesAsOf"))
    dims["benchmark"] = {"state": VALID if calc_ok else STALE,
                         "reason": None if calc_ok else "calc fingerprint/method version/base mismatch: recompute required"}
    qd = _date(block.get("quotesAsOf"))
    q_age = None if qd is None else (now.date() - qd).days
    ok_q = q_age is not None and -1 <= q_age <= quote_tolerance_days()
    dims["quote"] = {"state": VALID if ok_q else (STALE if qd else UNDETERMINED), "asOf": block.get("quotesAsOf"), "ageDays": q_age,
                     "reason": None if ok_q else "peer quotes older than tolerance: online reprice required"}
    usable = all(d["state"] == VALID for d in dims.values())
    first = next((f"{k}: {d['reason']}" for k, d in dims.items() if d["state"] != VALID), None)
    return {"usable": usable, "dimensions": dims, "reason": first, "excluded": dims["filing"].get("excluded", []), "validatedAt": block.get("validatedAt"),
            "method": block.get("method"), "fingerprints": fp}


def risk_signal_dimension(volatility_pct, max_drawdown_pct, price_observed_at, now: datetime) -> dict:
    """Freshness of the TARGET's price-history risk inputs; independent of benchmark and filings."""
    if volatility_pct is None or max_drawdown_pct is None:
        return {"state": UNDETERMINED, "reason": "risk inputs missing"}
    d = _date(price_observed_at)
    if d is None:
        return {"state": UNDETERMINED, "reason": "risk inputs undated"}
    age = (now.date() - d).days
    return {"state": VALID if age <= RISK_SIGNAL_MAX_AGE_DAYS else STALE, "ageDays": age,
            "reason": None if age <= RISK_SIGNAL_MAX_AGE_DAYS else "price history older than tolerance"}


# ---------------------------------------------------------------------------
# Validity models other than the benchmark (immutable evidence, quotes, decision)
# ---------------------------------------------------------------------------
CURRENT, HISTORICAL, SUPERSEDED = "CURRENT", "HISTORICAL", "SUPERSEDED"


def classify_filing(period_end, newest_known_period) -> dict:
    """A stored filing is immutable. It is CURRENT until a newer period is known, then SUPERSEDED (kept, readable)."""
    p, n = _date(period_end), _date(newest_known_period)
    if p is None:
        return {"state": UNDETERMINED, "reason": "filing period unknown", "retained": True}
    if n is not None and n > p:
        return {"state": SUPERSEDED, "supersededBy": n.isoformat(), "retained": True,
                "reason": "a newer filing period is known; this report remains stored evidence"}
    return {"state": CURRENT, "retained": True}


def quote_state(price_observed_at, now: datetime, tolerance_days: Optional[int] = None) -> dict:
    """CURRENT only when dated within tolerance. Anything older is HISTORICAL and must not feed a current valuation."""
    d = _date(price_observed_at)
    tol = tolerance_days if tolerance_days is not None else quote_tolerance_days()
    if d is None:
        return {"state": UNDETERMINED, "reason": "price undated"}
    age = (now.date() - d).days
    if age < -1:
        return {"state": UNDETERMINED, "ageDays": age, "reason": "price dated in the future"}
    return {"state": CURRENT if age <= tol else HISTORICAL, "ageDays": age, "asOf": d.isoformat()}


def decision_freshness(*, quote: dict, benchmark_usable: bool, filing: dict, risk: Optional[dict] = None) -> dict:
    """A decision is only as fresh as its weakest CRITICAL input; BUY requires all of them."""
    comps = {"quote": quote.get("state") == CURRENT, "benchmark": bool(benchmark_usable),
             "filing": filing.get("state") in (CURRENT, SUPERSEDED) and filing.get("state") != UNDETERMINED}
    if filing.get("state") == SUPERSEDED:
        comps["filing"] = False       # a superseded report may be shown, never used as the basis of a BUY
    if risk is not None:
        comps["risk"] = risk.get("state") == VALID
    blockers = sorted(k for k, ok in comps.items() if not ok)
    return {"buyAllowed": not blockers, "blockers": blockers, "components": comps}


def ledger_refresh_due(country: str, analyzed_at, period_end, now: datetime) -> bool:
    """Evidence-based re-analysis trigger: only when a newer filing can have appeared since the row was analysed."""
    a = _date(analyzed_at)
    p = _date(period_end)
    if a is None or p is None:
        return True            # cannot establish validity -> analyse (online) rather than assume
    return filing_may_have_changed(country, p, a, now.date())
