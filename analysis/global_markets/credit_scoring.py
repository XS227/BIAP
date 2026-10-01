"""Agent 10 credit scoring adapter for BIAP Global.

Canonical source:
  XS227/dma-agent
  branch: agent10-credit-scoring
  commit: 23e22225c5f575082e5f0e8eae5a30910a317c34
  file: decision_pipeline_credit.py

This module preserves the canonical Agent 10 formulas and thresholds while
adapting the inputs to BIAP GlobalCompany. Agent 10 is REPORT ONLY: it never
changes Agents 1-9, the investment score, or BUY/HOLD/AVOID decisions.

For legal entities, qualitative industry-risk/governance and FFO are never
invented. BIAP will use them only when an upstream verified/manual adapter
explicitly supplies them in raw_provider_fields under agent10_* keys.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .models import DistressAssessment, GlobalCompany

ENTITY_TYPES = ("individual", "legal_entity")
GOVERNANCE_LEVELS = ("strong", "satisfactory", "fair", "weak")

_RETAIL_INTERCEPT = -4.4
_RETAIL_COEF = {
    "missed_payment_share": 6.0,
    "credit_utilization": 1.5,
    "log_credit_history_years": -0.55,
    "debt_to_income": 2.0,
    "thin_file": 0.6,
    "many_accounts": 0.4,
    "bounced_checks": 0.35,
    "past_defaults": 0.8,
}
_RETAIL_REFERENCE = {
    "missed_payment_share": 0.03,
    "credit_utilization": 0.30,
    "debt_to_income": 0.36,
    "thin_file": 0.0,
    "many_accounts": 0.0,
    "bounced_checks": 0.0,
    "past_defaults": 0.0,
}
_RETAIL_REASONS = {
    "missed_payment_share": "Late or missed payments",
    "credit_utilization": "High revolving credit utilization",
    "debt_to_income": "High debt-to-income ratio",
    "thin_file": "Thin credit file (0-1 active accounts)",
    "many_accounts": "Many active accounts (10+)",
    "bounced_checks": "Bounced checks on record",
    "past_defaults": "Past default(s) on record",
}
_PDO, _BASE_SCORE, _BASE_ODDS = 20.0, 600.0, 50.0
_FACTOR = _PDO / math.log(2)
_OFFSET = _BASE_SCORE - _FACTOR * math.log(_BASE_ODDS)


def _retail_risk_band(pd_: float) -> str:
    if pd_ < 0.01:
        return "very low"
    if pd_ < 0.03:
        return "low"
    if pd_ < 0.08:
        return "moderate"
    if pd_ < 0.20:
        return "high"
    return "very high"


def score_individual_credit(
    *,
    payment_on_time_ratio: float,
    credit_utilization: float,
    credit_history_years: float,
    debt_to_income: float,
    active_accounts: float,
    bounced_checks: Optional[float] = None,
    past_defaults: Optional[float] = None,
) -> dict[str, Any]:
    """Canonical Agent 10 retail scorecard; illustrative, not lender-calibrated."""
    required = {
        "payment_on_time_ratio": payment_on_time_ratio,
        "credit_utilization": credit_utilization,
        "credit_history_years": credit_history_years,
        "debt_to_income": debt_to_income,
        "active_accounts": active_accounts,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        return {"model": "individual", "status": f"insufficient data (missing {', '.join(missing)} — not computed, not guessed)"}

    invalid = []
    if not 0 <= payment_on_time_ratio <= 1:
        invalid.append("payment_on_time_ratio must be a share between 0 and 1")
    for name, value in (
        ("credit_utilization", credit_utilization),
        ("credit_history_years", credit_history_years),
        ("debt_to_income", debt_to_income),
        ("active_accounts", active_accounts),
        ("bounced_checks", bounced_checks),
        ("past_defaults", past_defaults),
    ):
        if value is not None and value < 0:
            invalid.append(f"{name} cannot be negative")
    if invalid:
        return {"model": "individual", "status": "invalid input (" + "; ".join(invalid) + ") — not computed"}

    not_supplied = [
        name for name, value in (("bounced_checks", bounced_checks), ("past_defaults", past_defaults))
        if value is None
    ]
    x = {
        "missed_payment_share": 1 - payment_on_time_ratio,
        "credit_utilization": min(credit_utilization, 1.5),
        "log_credit_history_years": math.log1p(credit_history_years),
        "debt_to_income": min(debt_to_income, 1.5),
        "thin_file": 1.0 if active_accounts <= 1 else 0.0,
        "many_accounts": 1.0 if active_accounts >= 10 else 0.0,
        "bounced_checks": min(bounced_checks or 0, 5),
        "past_defaults": min(past_defaults or 0, 3),
    }
    contributions = {k: round(_RETAIL_COEF[k] * v, 4) for k, v in x.items()}
    z = _RETAIL_INTERCEPT + sum(_RETAIL_COEF[k] * v for k, v in x.items())
    pd_ = 1 / (1 + math.exp(-z))
    score = _OFFSET - _FACTOR * z
    excess = {k: _RETAIL_COEF[k] * (x[k] - ref) for k, ref in _RETAIL_REFERENCE.items()}
    reasons = [_RETAIL_REASONS[k] for k, d in sorted(excess.items(), key=lambda kv: -kv[1]) if d > 0][:4]

    out: dict[str, Any] = {
        "model": "individual",
        "log_odds": round(z, 3),
        "pd": round(pd_, 4),
        "score": round(score),
        "risk_band": _retail_risk_band(pd_),
        "contributions_to_log_odds": contributions,
        "reason_codes": reasons,
        "scaling": f"PDO={_PDO:g}, {_BASE_SCORE:g} points at {_BASE_ODDS:g}:1 good:bad odds",
        "source": (
            "Canonical DMA Agent 10 retail scorecard. Logistic scorecard/PDO scaling after "
            "Siddiqi (2017) and Thomas, Crook & Edelman (2017); coefficients illustrative, not fitted."
        ),
    }
    if not_supplied:
        out["adverse_history_not_supplied"] = not_supplied
        out["caveat"] = (
            f"{', '.join(not_supplied)} not supplied — scored as zero events, so PD may be "
            "understated if such records exist."
        )
    return out


_CATEGORY_SCORE = {"Aaa": 1, "Aa": 3, "A": 6, "Baa": 9, "Ba": 12, "B": 15, "Caa": 18, "Ca": 20}
_CATEGORIES = ("Aaa", "Aa", "A", "Baa", "Ba", "B", "Caa")
_GRID_HIGHER_BETTER = {
    "ebitda_interest": (20.0, 13.0, 8.0, 4.5, 2.5, 1.25, 0.5),
    "ffo_debt": (0.80, 0.60, 0.45, 0.30, 0.20, 0.12, 0.05),
    "fcf_debt": (0.25, 0.18, 0.12, 0.07, 0.03, 0.0, -0.05),
    "liquidity": (2.5, 2.0, 1.5, 1.2, 1.0, 0.8, 0.5),
}
_GRID_LOWER_BETTER = {"debt_ebitda": (0.75, 1.5, 2.25, 3.25, 4.5, 6.0, 8.0)}
_INDUSTRY_RISK = {1: "Aa", 2: "A", 3: "Baa", 4: "Ba", 5: "B", 6: "Caa"}
_GOVERNANCE = {"strong": "Aa", "satisfactory": "A", "fair": "Ba", "weak": "Caa"}
CORPORATE_WEIGHTS = {
    "industry_risk": 0.15,
    "debt_ebitda": 0.20,
    "ebitda_interest": 0.15,
    "ffo_debt": 0.15,
    "fcf_debt": 0.10,
    "liquidity": 0.10,
    "governance": 0.15,
}
_MIN_WEIGHT_COVERAGE = 0.60
_MOODYS_NOTCHES = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3",
                   "Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]
_SP_NOTCHES = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
               "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
_PD_ANCHORS = [(1, 0.0003), (3, 0.0003), (6, 0.0005), (9, 0.0015), (12, 0.006),
               (15, 0.031), (18, 0.26), (21, 0.26)]


def rating_pd(notch: int) -> float:
    for (n0, p0), (n1, p1) in zip(_PD_ANCHORS, _PD_ANCHORS[1:]):
        if n0 <= notch <= n1:
            t = (notch - n0) / (n1 - n0)
            return math.exp(math.log(p0) + t * (math.log(p1) - math.log(p0)))
    return _PD_ANCHORS[-1][1]


def _grid_category(metric: str, value: float) -> str:
    if metric in _GRID_LOWER_BETTER:
        for cat, cutoff in zip(_CATEGORIES, _GRID_LOWER_BETTER[metric]):
            if value < cutoff:
                return cat
        return "Ca"
    for cat, cutoff in zip(_CATEGORIES, _GRID_HIGHER_BETTER[metric]):
        if value >= cutoff:
            return cat
    return "Ca"


def _manual(company: GlobalCompany, key: str):
    raw = company.raw_provider_fields or {}
    for candidate in (f"agent10_{key}", key):
        if candidate in raw and raw[candidate] not in (None, ""):
            return raw[candidate]
    return None


def score_legal_entity_company(company: GlobalCompany, distress: Optional[DistressAssessment] = None) -> dict[str, Any]:
    """Canonical Agent 10 legal-entity grid adapted to one selected BIAP issuer."""
    if (company.sector or "").strip().lower() == "banking":
        return {
            "model": "legal_entity",
            "status": "not applicable — banks require a separate bank-rating methodology, not an EBITDA-based corporate grid",
            "report_only": True,
            "canonical_commit": "23e22225c5f575082e5f0e8eae5a30910a317c34",
        }

    ebitda = company.ebitda
    debt = company.total_debt
    interest = company.interest_expense
    ffo = _manual(company, "ffo")
    industry = _manual(company, "industry_risk")
    governance_raw = _manual(company, "governance")
    governance = str(governance_raw).strip().lower() if governance_raw not in (None, "") else None
    fcf = company.free_cash_flow

    scored: dict[str, dict] = {}
    missing: dict[str, str] = {}

    def put(name: str, value: Any, category: str, note: Optional[str] = None):
        row = {
            "value": None if value is None else (round(value, 4) if isinstance(value, (int, float)) else value),
            "category": category,
            "score": _CATEGORY_SCORE[category],
            "weight": CORPORATE_WEIGHTS[name],
        }
        if note:
            row["note"] = note
        scored[name] = row

    if ebitda is None or debt is None:
        missing["debt_ebitda"] = "missing " + ", ".join(
            name for name, value in (("ebitda", ebitda), ("total_debt", debt)) if value is None
        )
    elif ebitda <= 0:
        put("debt_ebitda", None, "Ca", "EBITDA is zero or negative — leverage multiple is not meaningful.")
    else:
        ratio = debt / ebitda
        put("debt_ebitda", ratio, _grid_category("debt_ebitda", ratio))

    if ebitda is None or interest is None:
        missing["ebitda_interest"] = "missing " + ", ".join(
            name for name, value in (("ebitda", ebitda), ("interest_expense", interest)) if value is None
        )
    elif ebitda <= 0:
        put("ebitda_interest", None, "Ca", "EBITDA is zero or negative — cannot cover interest from operations.")
    elif interest == 0:
        put("ebitda_interest", None, "Aaa", "No interest expense reported — coverage treated as unconstrained.")
    else:
        ratio = ebitda / abs(interest)
        put("ebitda_interest", ratio, _grid_category("ebitda_interest", ratio))

    if ffo is None or debt is None:
        missing["ffo_debt"] = "missing " + ", ".join(
            name for name, value in (("ffo", ffo), ("total_debt", debt)) if value is None
        )
    elif debt == 0:
        put("ffo_debt", None, "Aaa" if float(ffo) >= 0 else "Baa", "No debt — ratio undefined; scored on cash-flow sign.")
    else:
        ratio = float(ffo) / debt
        put("ffo_debt", ratio, _grid_category("ffo_debt", ratio))

    if fcf is None or debt is None:
        missing["fcf_debt"] = "missing " + ", ".join(
            name for name, value in (("free_cash_flow", fcf), ("total_debt", debt)) if value is None
        )
    elif debt == 0:
        put("fcf_debt", None, "Aaa" if fcf >= 0 else "Baa", "No debt — ratio undefined; scored on cash-flow sign.")
    else:
        ratio = fcf / debt
        put("fcf_debt", ratio, _grid_category("fcf_debt", ratio), "BIAP normalized free_cash_flow used as the canonical FCF numerator.")

    if company.current_assets is None or company.current_liabilities in (None, 0):
        missing["liquidity"] = "missing current_assets/current_liabilities"
    else:
        ratio = company.current_assets / company.current_liabilities
        put("liquidity", ratio, _grid_category("liquidity", ratio))

    try:
        industry_num = None if industry is None else float(industry)
    except (TypeError, ValueError):
        industry_num = None
    if industry is None:
        missing["industry_risk"] = "not supplied (analyst input, CICRA 1-6)"
    elif industry_num is None or int(industry_num) != industry_num or int(industry_num) not in _INDUSTRY_RISK:
        missing["industry_risk"] = f"invalid value {industry!r} (expected an integer 1-6)"
    else:
        put("industry_risk", industry_num, _INDUSTRY_RISK[int(industry_num)])

    if governance is None:
        missing["governance"] = "not supplied (analyst input: strong / satisfactory / fair / weak)"
    elif governance not in _GOVERNANCE:
        missing["governance"] = f"invalid value {governance!r} (expected strong / satisfactory / fair / weak)"
    else:
        put("governance", governance, _GOVERNANCE[governance], f"assessment: {governance}")

    coverage = sum(row["weight"] for row in scored.values())
    base = {
        "model": "legal_entity",
        "entity_type": "legal_entity",
        "report_only": True,
        "canonical_commit": "23e22225c5f575082e5f0e8eae5a30910a317c34",
        "weight_coverage": round(coverage, 2),
        "factors": scored,
        "factors_missing": missing,
        "source": (
            "Canonical DMA Agent 10 corporate factor grid after Moody's/S&P-style methodology; "
            "illustrative thresholds, not an agency rating."
        ),
    }

    if distress is not None:
        cross = {}
        if distress.synthetic_credit_band:
            cross["damodaran_icr_rating"] = distress.synthetic_credit_band
        if distress.distress_probability is not None:
            cross["zmijewski_p_distress"] = distress.distress_probability
        if cross:
            base["agent9_crosscheck"] = cross

    base["strict_rating_available"] = False
    base["strict_minimum_coverage"] = _MIN_WEIGHT_COVERAGE
    if coverage > 0:
        partial_aggregate = sum(row["score"] * row["weight"] for row in scored.values()) / coverage
        partial_notch = min(21, max(1, int(math.floor(partial_aggregate + 0.5))))
        partial = {
            "provisional": True,
            "not_for_decision": True,
            "coverage": round(coverage, 2),
            "leverage_scored": "debt_ebitda" in scored,
            "aggregate_score": round(partial_aggregate, 3),
            "status": "partial factors only — not a credit rating",
        }
        if coverage >= 0.20:
            partial["factor_band_moodys"] = _MOODYS_NOTCHES[partial_notch - 1]
            partial["factor_band_sp"] = _SP_NOTCHES[partial_notch - 1]
        base["partial_view"] = partial

    if "debt_ebitda" not in scored or coverage < _MIN_WEIGHT_COVERAGE:
        why = (
            "leverage (debt/EBITDA) not scored"
            if "debt_ebitda" not in scored
            else f"only {coverage:.0%} of the grid weight has data (needs {_MIN_WEIGHT_COVERAGE:.0%})"
        )
        base["status"] = f"insufficient data ({why} — strict rating not computed, missing inputs not guessed)"
        return base

    aggregate = sum(row["score"] * row["weight"] for row in scored.values()) / coverage
    notch = min(21, max(1, int(math.floor(aggregate + 0.5))))
    pd_ = rating_pd(notch)
    base.update({
        "strict_rating_available": True,
        "aggregate_score": round(aggregate, 3),
        "indicated_rating_moodys": _MOODYS_NOTCHES[notch - 1],
        "indicated_rating_sp": _SP_NOTCHES[notch - 1],
        "investment_grade": notch <= 10,
        "pd_1y": round(pd_, 5),
    })
    if missing:
        base["caveat"] = (
            f"{len(missing)} factor(s) without data; weights re-normalised over the "
            f"{coverage:.0%} of the grid that was scored."
        )
    return base
