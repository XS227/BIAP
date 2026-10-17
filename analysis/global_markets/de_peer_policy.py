"""Reviewed German peer-ledger policy: printed-value corrections (C) and the no-revenue-shell rule (B2).

Applied IN MEMORY to ledger rows at benchmark rebuild time; stored ledgers, fundamentals history and DMA assets are never
rewritten. Disabled unless BIAP_GLOBAL_DE_PEER_POLICY=1. Rules are evaluated on a row's STORED values against figures
printed in the issuer's own filing (data/de_peer_evidence.json; evidence: docs/validation/DE_OPTION_AB_COMPARISON_2026-10-17.md).

* strict  stored revenue > 0 -> period + revenue + net income found in the filing; revenue 0/None -> period + net income + printed EPS.
* C       replace a stored field by the printed value only when it is the same line item and unambiguous
          (revenue: stored is exactly the printed figure rounded to the provider's 10,000 step; net income: stored is
          'Gesamtergebnis'; EPS only together with a net-income correction). Definition-dependent revenue is never corrected.
* B2      stored revenue is exactly 0.0, the filing's income statement has no revenue line, period + net income match,
          and stored EPS reproduces to the cent from printed net income / printed shares.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

REGISTRY_PATH = Path(__file__).with_name("data") / "de_peer_evidence.json"
ENV_FLAG = "BIAP_GLOBAL_DE_PEER_POLICY"
ROUND_TOL = 5000.0      # provider rounds stored statement values to 10,000 -> half-step tolerance


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip() == "1"


@lru_cache(maxsize=1)
def registry() -> dict[str, dict[str, Any]]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if int(payload.get("schemaVersion") or 0) != 1:
        raise ValueError("unsupported DE peer evidence schema")
    rows = payload.get("issuers") or {}
    for isin, row in rows.items():
        if not isin.startswith("DE") or not str(row.get("source_url", "")).startswith("https://") or not row.get("sha256"):
            raise ValueError(f"incomplete DE peer evidence row {isin}")
    return rows


def near(stored: Optional[float], printed: Optional[float], tol: float = ROUND_TOL) -> bool:
    if stored is None or printed is None:
        return False
    return abs(stored - printed) <= min(tol, 0.02 * abs(printed))


def _cents(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x + 0.0, 2)


def _ni_ok(co: dict, f: dict) -> bool:
    return f.get("net_income") is not None and near(co.get("net_income"), f["net_income"]["printed"])


def _eps_printed_ok(co: dict, f: dict) -> bool:
    e = f.get("eps")
    return (bool(e) and e.get("basis_consistent_with_net_income", True) and co.get("eps") is not None
            and _cents(abs(co["eps"])) == _cents(abs(e["printed"])) and (co["eps"] < 0) == (e["printed"] < 0))


def _eps_derived_ok(co: dict, f: dict) -> bool:
    n, s = f.get("net_income"), f.get("shares")
    return bool(n and s) and co.get("eps") is not None and _cents(co["eps"]) == _cents(n["printed"] / s["printed"])


def _rev_positive(co: dict) -> bool:
    return co.get("revenue") not in (None, 0, 0.0)


def strict(co: dict, f: dict) -> bool:
    if not f.get("period_phrase_found"):
        return False
    if _rev_positive(co):
        return bool(f.get("revenue")) and near(co["revenue"], f["revenue"]["printed"]) and _ni_ok(co, f)
    return _ni_ok(co, f) and _eps_printed_ok(co, f)


def rule_b2(co: dict, f: dict) -> bool:
    return bool(f.get("period_phrase_found") and co.get("revenue") == 0 and f.get("revenue") is None
                and _ni_ok(co, f) and _eps_derived_ok(co, f))


def corrections(co: dict, f: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    r = f.get("revenue")
    if (r and not r.get("definition_ambiguous") and _rev_positive(co) and not near(co["revenue"], r["printed"])
            and co["revenue"] == round(r["printed"] / 10000.0) * 10000.0):
        out["revenue"] = r["printed"]
    n = f.get("net_income")
    if n and co.get("net_income") is not None and not near(co["net_income"], n["printed"]) and "Gesamtergebnis" in n["label"]:
        out["net_income"] = n["printed"]
    e = f.get("eps")
    if e and e.get("basis_consistent_with_net_income") and co.get("eps") is not None and "net_income" in out:
        out["eps"] = e["printed"]
    return out


def apply_correction(co: dict, new: dict[str, float]) -> dict:
    old_eps = co.get("eps")
    co.update(new)
    if "eps" in new and old_eps and co.get("pe") and co["pe"] > 0:
        co["pe"] = co["pe"] * old_eps / new["eps"]       # price unchanged: pe = price / eps
    return co


def apply_to_rows(rows: list[dict], evidence: Optional[dict[str, dict]] = None) -> dict[str, dict]:
    """Mutate the in-memory ledger rows; return an audit log {isin: {...}}. Rows already dated by a filing are untouched."""
    ev = registry() if evidence is None else evidence
    log: dict[str, dict] = {}
    for r in rows:
        co = r.get("company") or {}
        f = ev.get(co.get("isin"))
        if not f or co.get("filing_period_end"):
            continue
        new = corrections(co, f)
        if new:
            before = {k: co.get(k) for k in new}
            apply_correction(co, new)
            log[co["isin"]] = {"corrected": {k: {"stored": before[k], "printed": v} for k, v in new.items()}}
        rule = "strict" if strict(co, f) else ("B2" if rule_b2(co, f) else None)
        if rule:
            co["filing_period_end"] = f["period_end"]
            co["filing_evidence_ref"] = {"sha256": f["sha256"], "url": f["source_url"], "rule": rule}
            log.setdefault(co["isin"], {})["dated_by"] = rule
    return log
