"""Risk Agent (advisory, OFF by default).

Combines five published models/measures into ONE explainable risk level for a listed company:
Altman Z'' (1995), Ohlson O-score (1980), Zmijewski probit (1984), Beneish M-score (1999, 8 variables) and annualised price
volatility / drawdown. It is a read-only sidecar: it never changes score, tier, call, blocking gate or any stored ledger, and it
never invents an input. A model whose inputs are missing reports ``available=False`` with the missing field names.

Feature flag ``RISK_AGENT_ENABLED`` (default off). With the flag off, ``enabled()`` is False and the API route answers 404.
"""
from __future__ import annotations

import math
import os
from dataclasses import replace
from typing import Any, Mapping, Optional

from . import decision_logic, risk_inputs
from .distress import _is_financial, _logistic, is_capital_intensive, zmijewski_band, zmijewski_probability
from .models import GlobalCompany

FLAG = "RISK_AGENT_ENABLED"
VERSION = 2
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
# A company with none of these has no stored statements: price volatility alone never gives a level.
STATEMENT_FIELDS = ("total_assets", "total_liabilities", "total_equity", "current_assets", "current_liabilities", "retained_earnings",
                    "operating_income", "net_income", "operating_cash_flow", "revenue", "gross_profit", "total_debt", "interest_expense", "ebitda")
NO_STATEMENTS = "data not yet available: no stored financial statements for this company, so no level is given"

# Thresholds and rules live in data/risk_agent_config.json (override: env RISK_AGENT_CONFIG); nothing numeric is hard-coded below.
def cfg() -> dict:
    return risk_inputs.load_config()


# Severity of one signal: 0 = no flag, 1 = elevated, 2 = severe.
# Ohlson (1980), "Financial Ratios and the Probabilistic Prediction of Bankruptcy", Journal of Accounting Research 18(1), Table 4, Model 1
# (confirmed by the owner from the paper): SIZE = ln(total assets in US DOLLARS (units, not thousands) / GNP price-level index), index =
# US GDP implicit price deflator rebased 1968 = 100, taken for the year PRIOR to the balance-sheet year (data/us_gdp_deflator_gdpdef.json,
# FRED GDPDEF). Non-USD statements are converted at the statement-date FX rate. P = 1 / (1 + exp(-y)).
# Cut-offs (p.126): Ohlson notes that 0.5 has no basis; the cut-off that minimises total classification errors is 0.038. Both are CONFIG
# values (thresholds.ohlson_elevated = 0.038, thresholds.ohlson_severe = 0.50). Caveat: the model was estimated on 1970-76 US industrial
# firms, so for non-US firms and today's data it is indicative only (OHLSON_CAVEAT is shown with every O-score).
OHLSON_MODEL_1 = {"const": -1.32, "size": -0.407, "tlta": 6.03, "wcta": -1.43, "clca": 0.0757, "nita": -2.37, "futl": -1.83,
                  "intwo": 0.285, "oeneg": -1.72, "chin": -0.521}
OHLSON_CAVEAT = ("estimated by Ohlson (1980) on 1970-76 US industrial firms; for non-US firms and today's data it is indicative only")


def ohlson_y(size: float, tlta: float, wcta: float, clca: float, nita: float, futl: float, intwo: float, oeneg: float, chin: float) -> float:
    m = OHLSON_MODEL_1
    return (m["const"] + m["size"] * size + m["tlta"] * tlta + m["wcta"] * wcta + m["clca"] * clca + m["nita"] * nita + m["futl"] * futl
            + m["intwo"] * intwo + m["oeneg"] * oeneg + m["chin"] * chin)


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _signal(sid: str, name: str, *, available: bool, severity: int = 0, value: Any = None, band: Optional[str] = None,
            inputs: Optional[dict] = None, missing: Optional[list] = None, reason: str = "", applicable: bool = True) -> dict:
    return {"id": sid, "name": name, "available": available, "applicable": applicable, "severity": severity if available else 0,
            "value": None if value is None else round(float(value), 4), "band": band, "inputs": inputs or {},
            "missing": missing or [], "reason": reason}


def _missing(pairs: list) -> list:
    return [name for name, value in pairs if value is None]


# --- Altman Z'' ---------------------------------------------------------------------------------------------------------------
def altman_signal(company: GlobalCompany, c: Optional[dict] = None) -> dict:
    c = c or cfg()["thresholds"]
    name = "Altman Z''"
    fields = [("current_assets", company.current_assets), ("current_liabilities", company.current_liabilities),
              ("retained_earnings", company.retained_earnings), ("operating_income", company.operating_income),
              ("total_assets", company.total_assets), ("total_equity", company.total_equity), ("total_liabilities", company.total_liabilities)]
    miss = _missing(fields)
    ta, tl = _num(company.total_assets), _num(company.total_liabilities)
    if miss or not ta or not tl:
        return _signal("altman", name, available=False, missing=miss or [n for n, v in (("total_assets", ta), ("total_liabilities", tl)) if not v])
    wc = float(company.current_assets) - float(company.current_liabilities)
    z = (6.56 * wc / ta + 3.26 * float(company.retained_earnings) / ta + 6.72 * float(company.operating_income) / ta
         + 1.05 * float(company.total_equity) / tl)
    zone = "SAFE" if z > c["altman_safe"] else "GREY" if z >= c["altman_distress"] else "DISTRESS"
    severity = {"SAFE": 0, "GREY": 1, "DISTRESS": 2}[zone]
    reason = f"Altman Z''={z:.2f} ({zone.lower()} zone)"
    if zone == "DISTRESS" and decision_logic.is_v2() and is_capital_intensive(company):
        severity = 1                                  # same guard as distress_agent (P1.8): structurally high liabilities
        reason += "; capital-intensive sector, so the distress zone is treated as elevated, not severe"
    return _signal("altman", name, available=True, severity=severity, value=z, band=zone,
                   inputs={"working_capital_to_assets": wc / ta, "retained_earnings_to_assets": float(company.retained_earnings) / ta,
                           "ebit_to_assets": float(company.operating_income) / ta, "equity_to_liabilities": float(company.total_equity) / tl},
                   reason=reason)


# --- Zmijewski probit -----------------------------------------------------------------------------------------------------------
def zmijewski_signal(company: GlobalCompany, c: Optional[dict] = None) -> dict:
    c = c or cfg()["thresholds"]
    name = "Zmijewski"
    fields = [("net_income", company.net_income), ("total_assets", company.total_assets), ("total_liabilities", company.total_liabilities),
              ("current_assets", company.current_assets), ("current_liabilities", company.current_liabilities)]
    miss = _missing(fields)
    ta, cl = _num(company.total_assets), _num(company.current_liabilities)
    if miss or not ta or not cl:
        return _signal("zmijewski", name, available=False, missing=miss or [n for n, v in (("total_assets", ta), ("current_liabilities", cl)) if not v])
    ni_ta, tl_ta, ca_cl = float(company.net_income) / ta, float(company.total_liabilities) / ta, float(company.current_assets) / cl
    index = -4.3 - 4.5 * ni_ta + 5.7 * tl_ta - 0.004 * ca_cl
    p = zmijewski_probability(index)                  # probit under v2 (Zmijewski 1984), logistic under frozen v1
    severity = 2 if p >= c["zmijewski_severe"] else 1 if p >= c["zmijewski_elevated"] else 0
    return _signal("zmijewski", name, available=True, severity=severity, value=p, band=zmijewski_band(p),
                   inputs={"index": index, "net_income_to_assets": ni_ta, "liabilities_to_assets": tl_ta, "current_ratio": ca_cl,
                           "link": "probit" if decision_logic.is_v2() else "logistic (v1)"},
                   reason=f"Zmijewski P(distress)={p:.3f} ({zmijewski_band(p)})")


# --- Ohlson O-score ---------------------------------------------------------------------------------------------------------------
def _prior_net_income(company: GlobalCompany, prior: Optional[Mapping]) -> Optional[float]:
    if prior and _num(prior.get("net_income_prev")) is not None:
        return _num(prior.get("net_income_prev"))
    margin, revenue = _num(company.net_margin_prev_pct), _num(company.revenue_prev)
    return None if margin is None or revenue is None else margin * revenue / 100.0


def ohlson_signal(company: GlobalCompany, prior: Optional[Mapping] = None, fx: Optional[Mapping] = None,
                  scale: Optional[Mapping] = None, c: Optional[dict] = None) -> dict:
    """O = -1.32 -0.407 SIZE +6.03 TLTA -1.43 WCTA +0.0757 CLCA -1.72 OENEG -2.37 NITA -1.83 FUTL +0.285 INTWO -0.521 CHIN; P = logistic(O).

    SIZE = ln( total assets in USD, converted at the FX rate of the statement date, / US GDP deflator (1968 = 100) of the year PRIOR to the
    balance-sheet year ). FUTL uses operating cash flow as the funds-from-operations proxy. ``fx`` is risk_inputs.statement_fx(); ``scale`` is
    risk_inputs.statement_scale(): SIZE is only computed when the statement is in verified/inferred full currency units."""
    c = c or cfg()["thresholds"]
    name = "Ohlson O-score"
    ni_prev = _prior_net_income(company, prior)
    fields = [("total_assets", company.total_assets), ("total_liabilities", company.total_liabilities), ("current_assets", company.current_assets),
              ("current_liabilities", company.current_liabilities), ("net_income", company.net_income),
              ("operating_cash_flow", company.operating_cash_flow), ("net_income_prior_year", ni_prev)]
    miss = _missing(fields)
    ta, cl = _num(company.total_assets), _num(company.current_liabilities)
    ca = _num(company.current_assets)
    if not miss and (not ta or ta <= 0 or not cl or not ca):
        miss = [n for n, v in (("total_assets", ta), ("current_liabilities", cl), ("current_assets", ca)) if not v or v <= 0]
    flags: list = []
    fx = fx or {}
    if not fx.get("ok"):
        miss.append("fx_at_statement_date")
        flags.append(fx.get("reason") or "statement-date FX not supplied")
    scale = scale or {"status": "UNKNOWN", "flags": ["statement unit scale not checked"]}
    if scale.get("status") not in ("VERIFIED", "INFERRED"):
        miss.append("statement_unit_scale")
        flags += list(scale.get("flags") or [])
    year = None
    try:
        year = int(str(company.filing_period_end)[:4])
    except (TypeError, ValueError):
        pass
    defl = risk_inputs.deflator_index(year - 1) if year else None          # Ohlson: index of the year PRIOR to the balance-sheet year
    if defl is None:
        miss.append("us_gdp_deflator_for_prior_year")
        flags.append(f"no GDP deflator for the year before the statement year {year}")
    if miss:
        sig = _signal("ohlson", name, available=False, missing=miss)
        sig["flags"], sig["unitScale"] = flags, scale.get("status")
        return sig
    tl, ni, ocf = float(company.total_liabilities), float(company.net_income), float(company.operating_cash_flow)
    ohl_cfg = cfg().get("ohlson", {})
    unit = float(ohl_cfg.get("asset_unit_usd", 1.0))                      # 1 = total assets in US dollars (Ohlson 1980)
    ta_usd = ta * float(fx["rate"]) / unit
    size = math.log(ta_usd / defl["index"])
    tlta, wcta, clca = tl / ta, (ca - cl) / ta, cl / ca
    oeneg = 1.0 if tl > ta else 0.0
    nita, futl = ni / ta, (ocf / tl if tl else 0.0)
    intwo = 1.0 if (ni < 0 and ni_prev < 0) else 0.0
    denom = abs(ni) + abs(ni_prev)
    chin = (ni - ni_prev) / denom if denom else 0.0
    o = ohlson_y(size, tlta, wcta, clca, nita, futl, intwo, oeneg, chin)
    p = _logistic(o)
    severity = 2 if p >= c["ohlson_severe"] else 1 if p >= c["ohlson_elevated"] else 0
    band = "high" if severity == 2 else "elevated" if severity == 1 else "low"
    if defl["partial"]:
        flags.append(f"GDP deflator for {year - 1} is a partial-year average")
    sig = _signal("ohlson", name, available=True, severity=severity, value=p, band=band,
                  inputs={"o_score": o, "size": size, "total_assets_usd": ta_usd, "fx_rate_to_usd": fx["rate"],
                          "fx_rate_date": fx["rateDate"], "gdp_deflator_1968_100": defl["index"], "deflator_year": year - 1,
                          "tlta": tlta, "wcta": wcta, "clca": clca, "oeneg": oeneg, "nita": nita, "futl_ocf_proxy": futl, "intwo": intwo,
                          "chin": chin},
                  reason=f"Ohlson P(bankruptcy)={p:.3f} (O={o:.2f})")
    sig["assetUnitUsd"], sig["caveat"] = unit, OHLSON_CAVEAT
    sig["flags"], sig["unitScale"] = flags, scale.get("status")
    return sig


# --- Beneish M-score (needs two years of statement items; BIAP stores only the current year today) ---------------------------------
BENEISH_ITEMS = ("receivables", "revenue", "gross_profit", "ppe", "depreciation", "sga", "total_assets", "total_debt")


def beneish_signal(company: GlobalCompany, history: Optional[Mapping] = None, c: Optional[dict] = None) -> dict:
    c_th = c or cfg()["thresholds"]
    threshold = c_th["beneish"]
    """``history`` supplies what the company record lacks: ``receivables``, ``ppe``, ``depreciation``, ``sga`` for the current year and
    every item of BENEISH_ITEMS with a ``_prev`` suffix (e.g. ``revenue_prev``). Revenue, gross profit, total assets and total debt of
    the current year come from the company record unless ``history`` overrides them."""
    name = "Beneish M-score"
    h = history or {}
    own = {"revenue": company.revenue, "gross_profit": company.gross_profit, "total_assets": company.total_assets, "total_debt": company.total_debt}
    c = {k: _num(h.get(k, own.get(k))) for k in BENEISH_ITEMS}  # (c = current-year items)
    p = {k: _num(h.get(k + "_prev", company.revenue_prev if k == "revenue" else None)) for k in BENEISH_ITEMS}
    c["net_income"], c["operating_cash_flow"] = _num(company.net_income), _num(company.operating_cash_flow)
    miss = [k for k in BENEISH_ITEMS if c[k] is None] + [k + "_prev" for k in BENEISH_ITEMS if p[k] is None]
    miss += [k for k in ("net_income", "operating_cash_flow") if c[k] is None]
    if miss:
        return _signal("beneish", name, available=False, missing=miss)
    try:
        dsri = (c["receivables"] / c["revenue"]) / (p["receivables"] / p["revenue"])
        gmi = (p["gross_profit"] / p["revenue"]) / (c["gross_profit"] / c["revenue"])
        aqi = (1 - c["ppe"] / c["total_assets"]) / (1 - p["ppe"] / p["total_assets"])
        sgi = c["revenue"] / p["revenue"]
        depi = (p["depreciation"] / (p["depreciation"] + p["ppe"])) / (c["depreciation"] / (c["depreciation"] + c["ppe"]))
        sgai = (c["sga"] / c["revenue"]) / (p["sga"] / p["revenue"])
        lvgi = (c["total_debt"] / c["total_assets"]) / (p["total_debt"] / p["total_assets"])
        tata = (c["net_income"] - c["operating_cash_flow"]) / c["total_assets"]
    except ZeroDivisionError:
        return _signal("beneish", name, available=False, missing=["non_zero_denominators"])
    m = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    flagged = m > threshold
    return _signal("beneish", name, available=True, severity=1 if flagged else 0, value=m, band="manipulation-risk" if flagged else "unlikely",
                   inputs={"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi, "SGAI": sgai, "LVGI": lvgi, "TATA": tata},
                   reason=f"Beneish M={m:.2f} ({'above' if flagged else 'below'} the {threshold} cut-off; earnings-quality flag, not a solvency measure)")


# --- price volatility ---------------------------------------------------------------------------------------------------------
def volatility_signal(company: GlobalCompany, c: Optional[dict] = None) -> dict:
    c = c or cfg()["thresholds"]
    vol, dd = _num(company.volatility_annualized_pct), _num(company.max_drawdown_pct)
    if vol is None and dd is None:
        return _signal("volatility", "Price volatility", available=False, missing=["volatility_annualized_pct", "max_drawdown_pct"])
    dd = abs(dd) if dd is not None else None
    flagged = (vol is not None and vol >= c["volatility_elevated_pct"]) or (dd is not None and dd >= c["drawdown_elevated_pct"])
    parts = [f"annualised volatility {vol:.0f}%" if vol is not None else None, f"max drawdown {dd:.0f}%" if dd is not None else None]
    return _signal("volatility", "Price volatility", available=True, severity=1 if flagged else 0, value=vol if vol is not None else dd,
                   band="high" if flagged else "normal", inputs={"volatility_annualized_pct": vol, "max_drawdown_pct": dd},
                   reason=", ".join(p for p in parts if p) + (" (price-risk flag; capped at elevated)" if flagged else ""))


# --- IFRS 16 leases -----------------------------------------------------------------------------------------------------------
def lease_adjustments(company: GlobalCompany, conf: Optional[Mapping] = None) -> dict:
    """Non-US (IFRS) filers: lease liabilities belong in debt and lease interest in the interest bill. US GAAP operating leases are not
    comparable and are left alone. Total liabilities (TLTA, Altman, Zmijewski) already contain IFRS 16 lease liabilities when the filing's
    own Liabilities total is used, so TLTA is only corrected if the stored total is smaller than borrowings + leases (a data defect)."""
    conf = conf or cfg()
    out = {"applied": False, "notes": [], "debt_incl_leases": _num(company.total_debt), "interest_expense": _num(company.interest_expense),
           "lease_liabilities": _num(company.lease_liabilities), "lease_interest": _num(company.lease_interest_expense),
           "total_liabilities": _num(company.total_liabilities)}
    if not conf.get("leases", {}).get("ifrs16_non_us", True) or str(company.country).upper() == "US":
        out["notes"].append("IFRS 16 adjustment not applied (US GAAP issuer or disabled in config)")
        return out
    lease, lease_int, basis = out["lease_liabilities"], out["lease_interest"], company.interest_expense_basis
    if lease is None:
        out["notes"].append("lease liabilities not tagged/extracted: debt and TLTA exclude leases only if the filer reports them elsewhere")
    else:
        out["debt_incl_leases"] = lease if out["debt_incl_leases"] is None else out["debt_incl_leases"] + lease
        out["applied"] = True
        if company.total_debt is None:
            out["notes"].append("borrowings not tagged: debt incl. leases is lease liabilities only")
        tl = out["total_liabilities"]
        if tl is not None and out["debt_incl_leases"] is not None and tl < out["debt_incl_leases"]:
            out["total_liabilities"] = out["debt_incl_leases"]
            out["notes"].append(f"stored total liabilities ({tl:,.0f}) is below debt incl. leases; total liabilities raised to {out['debt_incl_leases']:,.0f}")
    if lease_int is not None and out["interest_expense"] is not None:
        if basis == "InterestExpense":
            out["interest_expense"] += abs(lease_int)
            out["applied"] = True
            out["notes"].append("lease interest added to the InterestExpense tag (possible double count if the tag already includes it)")
        else:
            out["notes"].append(f"interest taken from {basis or 'an unknown tag'}: lease interest is part of finance costs, not added again")
    elif lease_int is None and basis == "InterestExpense":
        out["notes"].append("interest from the InterestExpense tag and lease interest not tagged: coverage may exclude lease interest")
    return out


# --- interest coverage (supporting signal) ---------------------------------------------------------------------------------------
def interest_coverage_signal(company: GlobalCompany, c: Optional[dict] = None, leases: Optional[Mapping] = None) -> dict:
    """EBIT / interest expense (IFRS 16 adjusted for non-US filers, see lease_adjustments). Supporting signal: below the elevated limit =
    elevated, below the severe limit = severe. Same limits as Agent 9. It is not one of the three solvency models (does not count for
    data sufficiency) and a severe value alone can reach HIGH, never CRITICAL."""
    c = c or cfg()["thresholds"]
    leases = leases or lease_adjustments(company)
    name = "Interest coverage"
    ebit, ie = _num(company.operating_income), leases.get("interest_expense")
    miss = (["operating_income"] if ebit is None else []) + (["interest_expense"] if ie in (None, 0) else [])
    if miss:
        return _signal("interest_coverage", name, available=False, missing=miss)
    icr = ebit / abs(ie)
    severity = 2 if icr < c["interest_coverage_severe"] else 1 if icr < c["interest_coverage_elevated"] else 0
    band = "severe" if severity == 2 else "elevated" if severity == 1 else "adequate"
    debt, ebitda = leases.get("debt_incl_leases"), _num(company.ebitda)
    inputs = {"ebit": ebit, "interest_expense": abs(ie), "interest_expense_reported": _num(company.interest_expense),
              "debt_incl_leases": debt, "lease_liabilities": leases.get("lease_liabilities"),
              "debt_incl_leases_to_ebitda": (debt / ebitda if debt is not None and ebitda and ebitda > 0 else None)}
    sig = _signal("interest_coverage", name, available=True, severity=severity, value=icr, band=band,
                  inputs=inputs, reason=f"Interest coverage EBIT/interest={icr:.2f}x ({band})")
    sig["flags"] = list(leases.get("notes") or [])
    return sig


# --- aggregation ----------------------------------------------------------------------------------------------------------------
def _hard_reasons(company: GlobalCompany) -> list:
    out = []
    if company.total_equity is not None and company.total_equity < 0:
        out.append("negative total equity")
    text = " ".join([company.audit_opinion or "", *[str(x) for x in company.material_event_flags]]).lower()
    if "going concern" in text:
        out.append("going-concern warning")
    return out


def statement_defects(company: GlobalCompany) -> list:
    """Impossible balance-sheet values (extraction/unit errors). Such a statement must not produce a level.

    total assets <= 0; negative liabilities; equity above total assets (that would need negative liabilities); liabilities above 50x assets.
    Negative equity with positive assets is legitimate (buy-backs, accumulated losses) and is not a defect.
    """
    ta, tl, te = _num(company.total_assets), _num(company.total_liabilities), _num(company.total_equity)
    out = []
    if ta is not None and ta <= 0:
        out.append("total assets <= 0")
    elif ta is not None:
        if tl is not None and tl < 0:
            out.append("negative liabilities")
        if te is not None and te > ta * 1.01:
            out.append("equity above total assets")
        if tl is not None and tl > ta * 50:
            out.append("liabilities above 50x assets")
    return out


def assess(company: GlobalCompany, *, history: Optional[Mapping] = None, fx: Optional[Mapping] = None,
           scale: Optional[Mapping] = None, config: Optional[Mapping] = None) -> dict:
    """Risk level for one enriched company. Pure function: no network, no writes (``fx``/``scale`` are resolved by the caller)."""
    conf = config or cfg()
    th, rules = conf["thresholds"], conf["rules"]
    min_models = int(rules["min_solvency_models"])
    hard = _hard_reasons(company)
    leases = None
    financial = _is_financial(company)
    vol = volatility_signal(company, th)
    na = "not applicable: financial institution (generic corporate distress/earnings models are suppressed for banks and insurers)"
    if financial:
        models = [_signal(i, n, available=False, applicable=False, reason=na)
                  for i, n in (("altman", "Altman Z''"), ("ohlson", "Ohlson O-score"), ("zmijewski", "Zmijewski"), ("beneish", "Beneish M-score"))]
        icr = _signal("interest_coverage", "Interest coverage", available=False, applicable=False, reason=na)
    else:
        leases = lease_adjustments(company, conf)
        adj = company
        if leases["total_liabilities"] is not None and leases["total_liabilities"] != _num(company.total_liabilities):
            adj = replace(company, total_liabilities=leases["total_liabilities"])     # IFRS 16 data-defect correction (see lease_adjustments)
        models = [altman_signal(adj, th), ohlson_signal(adj, history, fx, scale, th), zmijewski_signal(adj, th), beneish_signal(company, history, th)]
        icr = interest_coverage_signal(company, th, leases)
    signals = models + [icr, vol]
    solvency = [s for s in models if s["id"] in ("altman", "ohlson", "zmijewski") and s["available"]]
    # D2 (owner-approved 2026-11-27). Severe signals counted: Altman, Ohlson, Zmijewski, interest coverage (Beneish and price volatility are
    # not severe-capable). Elevated signs: the same four plus price volatility, plus negative equity when configured.
    counted = [s for s in (models[0], models[1], models[2], icr) if s["available"]]
    severe = [s for s in counted if s["severity"] == 2]
    elevated_signs = [s for s in counted + ([vol] if vol["available"] else []) if s["severity"] >= 1]
    neg_equity = "negative total equity" in hard
    going_concern = "going-concern warning" in hard
    n_elevated = len(elevated_signs) + (1 if neg_equity and rules.get("negative_equity_is_elevated_sign", True) else 0)
    any_flag = bool(hard) or any(s["available"] and s["severity"] >= 1 for s in signals)

    defects = [] if financial else statement_defects(company)
    no_statements = all(_num(getattr(company, f)) is None for f in STATEMENT_FIELDS)
    reasons = [f"{h} (hard reason)" for h in hard]
    reasons += [s["reason"] for s in signals if s["available"] and s["severity"] >= 1]
    watch: list = []
    level: Optional[str]
    if defects:
        level = None                                  # impossible statement values (data defect): no level rather than a wrong one
    elif going_concern or (len(severe) >= int(rules["critical_min_severe"]) and neg_equity):
        level = "CRITICAL"
    elif no_statements:
        level = None
    elif len(severe) >= int(rules["high_min_severe"]):
        level = "HIGH"
    elif len(severe) >= int(rules["medium_min_severe"]) or n_elevated >= int(rules["medium_min_elevated"]):
        level = "MEDIUM"
    elif (financial and any_flag) or (not financial and (len(solvency) >= min_models or any_flag)):
        level = "LOW"                                 # a single elevated sign stays LOW, with a watch note
        if n_elevated == 1:
            watch = [s["reason"] for s in elevated_signs] + (["negative total equity"] if neg_equity else [])
    else:
        level = None
    partial = not financial and len(solvency) < min_models
    if level is None:
        status = "NOT_APPLICABLE" if financial else "INSUFFICIENT_DATA"
        if defects:
            reasons = [f"statement values are impossible ({'; '.join(defects)}), so the stored statements are not used and no level is given"]
        elif no_statements:
            reasons.insert(0, NO_STATEMENTS)
        else:
            reasons.append(na if financial else f"fewer than {min_models} solvency models (Altman, Ohlson, Zmijewski) have their inputs; no level is given")
    else:
        status = "PARTIAL" if partial else "OK"
        if level == "LOW":
            reasons.append("no model flags the company" if not watch else "watch: a single elevated sign does not raise the level")
        if partial:
            reasons.append(f"statements are partial ({len(solvency)} of 3 solvency models have their inputs): this level rests on incomplete data"
                           + ("; LOW is not a clean result" if level == "LOW" else ""))
    prelim = {str(x).upper() for x in (rules.get("calibration") or {}).get("preliminary", ["US"])}
    calibration = "unavailable" if level is None else "preliminary" if str(company.country).upper() in prelim else "not_calibrated"
    flags = (list(signals[1].get("flags") or []) + list(icr.get("flags") or [])) if not financial else []
    return {"agent": "risk", "version": VERSION, "advisoryOnly": True, "level": level, "status": status, "reasons": reasons,
            "hardReasons": hard, "dataNotYetAvailable": level is None and no_statements, "watch": watch, "calibration": calibration, "signals": signals, "flags": flags, "leases": leases if not financial else None,
            "dataSufficiency": {"solvencyModelsAvailable": len(solvency), "required": min_models,
                                "missing": {s["id"]: s["missing"] for s in signals if s["missing"] and s["applicable"]}},
            "config": {"path": conf.get("_path"), "version": conf.get("version"), "thresholds": th},
            "unitScale": {k: v for k, v in (scale or {}).items() if k != "flags"} or None,
            "fx": dict(fx) if fx else None,
            "decisionLogicVersion": decision_logic.logic_version(),
            "asOf": {"filingPeriodEnd": company.filing_period_end, "priceObservedAt": company.price_observed_at},
            "disclaimer": "Research aid on stored statements and prices. Not a credit rating, not a forecast and not investment advice; "
                          "it does not change any BIAP score, tier or call."}
