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
from typing import Any, Mapping, Optional

from . import decision_logic
from .distress import _is_financial, _logistic, is_capital_intensive, zmijewski_band, zmijewski_probability
from .models import GlobalCompany

FLAG = "RISK_AGENT_ENABLED"
VERSION = 1
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# Severity of one signal: 0 = no flag, 1 = elevated, 2 = severe.
ALTMAN_SAFE, ALTMAN_DISTRESS = 2.6, 1.1                       # Altman Z'' zones (canonical, same as distress.py)
ZMIJEWSKI_SEVERE, ZMIJEWSKI_ELEVATED = 0.5, 0.35              # same limits as distress_agent
OHLSON_SEVERE, OHLSON_ELEVATED = 0.5, 0.25                    # OWNER DECISION (Ohlson's own 0.038 cut-off is a classification cut-off, far too sensitive)
BENEISH_THRESHOLD = -1.78                                     # Beneish (1999) 8-variable cut-off; flags earnings-manipulation risk only
VOL_ELEVATED_PCT, DRAWDOWN_ELEVATED_PCT = 50.0, 50.0          # price-risk flag; never "severe" on its own
# Ohlson SIZE = ln(total assets in USD thousands / price-level index). Ohlson used the 1968=100 GNP deflator; the modern value is an
# approximation and an OWNER DECISION (a wrong index shifts every O-score by a constant).
OHLSON_PRICE_INDEX = 680.0
MIN_SOLVENCY_MODELS = 2


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
def altman_signal(company: GlobalCompany) -> dict:
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
    zone = "SAFE" if z > ALTMAN_SAFE else "GREY" if z >= ALTMAN_DISTRESS else "DISTRESS"
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
def zmijewski_signal(company: GlobalCompany) -> dict:
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
    severity = 2 if p >= ZMIJEWSKI_SEVERE else 1 if p >= ZMIJEWSKI_ELEVATED else 0
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


def ohlson_signal(company: GlobalCompany, prior: Optional[Mapping] = None, fx_to_usd: Optional[float] = None) -> dict:
    """O = -1.32 -0.407 SIZE +6.03 TLTA -1.43 WCTA +0.0757 CLCA -1.72 OENEG -2.37 NITA -1.83 FUTL +0.285 INTWO -0.521 CHIN; P = logistic(O).

    FUTL uses operating cash flow as the funds-from-operations proxy. ``fx_to_usd`` converts the reporting currency to USD for SIZE.
    """
    name = "Ohlson O-score"
    ni_prev = _prior_net_income(company, prior)
    fields = [("total_assets", company.total_assets), ("total_liabilities", company.total_liabilities), ("current_assets", company.current_assets),
              ("current_liabilities", company.current_liabilities), ("net_income", company.net_income),
              ("operating_cash_flow", company.operating_cash_flow), ("net_income_prior_year", ni_prev), ("fx_to_usd", fx_to_usd)]
    miss = _missing(fields)
    ta, cl = _num(company.total_assets), _num(company.current_liabilities)
    ca = _num(company.current_assets)
    if not miss and (not ta or ta <= 0 or not cl or not ca or not fx_to_usd or fx_to_usd <= 0):
        miss = [n for n, v in (("total_assets", ta), ("current_liabilities", cl), ("current_assets", ca), ("fx_to_usd", fx_to_usd)) if not v or v <= 0]
    if miss:
        return _signal("ohlson", name, available=False, missing=miss)
    tl, ni, ocf = float(company.total_liabilities), float(company.net_income), float(company.operating_cash_flow)
    size = math.log(ta * fx_to_usd / 1000.0 / OHLSON_PRICE_INDEX)
    tlta, wcta, clca = tl / ta, (ca - cl) / ta, cl / ca
    oeneg = 1.0 if tl > ta else 0.0
    nita, futl = ni / ta, (ocf / tl if tl else 0.0)
    intwo = 1.0 if (ni < 0 and ni_prev < 0) else 0.0
    denom = abs(ni) + abs(ni_prev)
    chin = (ni - ni_prev) / denom if denom else 0.0
    o = (-1.32 - 0.407 * size + 6.03 * tlta - 1.43 * wcta + 0.0757 * clca - 1.72 * oeneg - 2.37 * nita - 1.83 * futl
         + 0.285 * intwo - 0.521 * chin)
    p = _logistic(o)
    severity = 2 if p >= OHLSON_SEVERE else 1 if p >= OHLSON_ELEVATED else 0
    band = "high" if severity == 2 else "elevated" if severity == 1 else "low"
    return _signal("ohlson", name, available=True, severity=severity, value=p, band=band,
                   inputs={"o_score": o, "size": size, "tlta": tlta, "wcta": wcta, "clca": clca, "oeneg": oeneg, "nita": nita,
                           "futl_ocf_proxy": futl, "intwo": intwo, "chin": chin, "price_index": OHLSON_PRICE_INDEX},
                   reason=f"Ohlson P(bankruptcy)={p:.3f} (O={o:.2f}; size term uses an approximate price-level index)")


# --- Beneish M-score (needs two years of statement items; BIAP stores only the current year today) ---------------------------------
BENEISH_ITEMS = ("receivables", "revenue", "gross_profit", "ppe", "depreciation", "sga", "total_assets", "total_debt")


def beneish_signal(company: GlobalCompany, history: Optional[Mapping] = None) -> dict:
    """``history`` supplies what the company record lacks: ``receivables``, ``ppe``, ``depreciation``, ``sga`` for the current year and
    every item of BENEISH_ITEMS with a ``_prev`` suffix (e.g. ``revenue_prev``). Revenue, gross profit, total assets and total debt of
    the current year come from the company record unless ``history`` overrides them."""
    name = "Beneish M-score"
    h = history or {}
    own = {"revenue": company.revenue, "gross_profit": company.gross_profit, "total_assets": company.total_assets, "total_debt": company.total_debt}
    c = {k: _num(h.get(k, own.get(k))) for k in BENEISH_ITEMS}
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
    flagged = m > BENEISH_THRESHOLD
    return _signal("beneish", name, available=True, severity=1 if flagged else 0, value=m, band="manipulation-risk" if flagged else "unlikely",
                   inputs={"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi, "SGAI": sgai, "LVGI": lvgi, "TATA": tata},
                   reason=f"Beneish M={m:.2f} ({'above' if flagged else 'below'} the {BENEISH_THRESHOLD} cut-off; earnings-quality flag, not a solvency measure)")


# --- price volatility ---------------------------------------------------------------------------------------------------------
def volatility_signal(company: GlobalCompany) -> dict:
    vol, dd = _num(company.volatility_annualized_pct), _num(company.max_drawdown_pct)
    if vol is None and dd is None:
        return _signal("volatility", "Price volatility", available=False, missing=["volatility_annualized_pct", "max_drawdown_pct"])
    dd = abs(dd) if dd is not None else None
    flagged = (vol is not None and vol >= VOL_ELEVATED_PCT) or (dd is not None and dd >= DRAWDOWN_ELEVATED_PCT)
    parts = [f"annualised volatility {vol:.0f}%" if vol is not None else None, f"max drawdown {dd:.0f}%" if dd is not None else None]
    return _signal("volatility", "Price volatility", available=True, severity=1 if flagged else 0, value=vol if vol is not None else dd,
                   band="high" if flagged else "normal", inputs={"volatility_annualized_pct": vol, "max_drawdown_pct": dd},
                   reason=", ".join(p for p in parts if p) + (" (price-risk flag; capped at elevated)" if flagged else ""))


# --- aggregation ----------------------------------------------------------------------------------------------------------------
def _hard_reasons(company: GlobalCompany) -> list:
    out = []
    if company.total_equity is not None and company.total_equity < 0:
        out.append("negative total equity")
    text = " ".join([company.audit_opinion or "", *[str(x) for x in company.material_event_flags]]).lower()
    if "going concern" in text:
        out.append("going-concern warning")
    return out


def assess(company: GlobalCompany, *, history: Optional[Mapping] = None, fx_to_usd: Optional[float] = None) -> dict:
    """Risk level for one enriched company. Pure function: no network, no writes."""
    hard = _hard_reasons(company)
    financial = _is_financial(company)
    vol = volatility_signal(company)
    na = "generic corporate distress/earnings models are suppressed for financial-sector issuers"
    if financial:
        models = [_signal(i, n, available=False, applicable=False, reason=na)
                  for i, n in (("altman", "Altman Z''"), ("ohlson", "Ohlson O-score"), ("zmijewski", "Zmijewski"), ("beneish", "Beneish M-score"))]
    else:
        models = [altman_signal(company), ohlson_signal(company, history, fx_to_usd), zmijewski_signal(company), beneish_signal(company, history)]
    signals = models + [vol]
    solvency = [s for s in models if s["id"] in ("altman", "ohlson", "zmijewski") and s["available"]]
    severe = [s for s in solvency if s["severity"] == 2]
    elevated = [s for s in signals if s["available"] and s["severity"] == 1]

    reasons = [f"{h} (hard reason)" for h in hard]
    reasons += [s["reason"] for s in signals if s["available"] and s["severity"] >= 1]
    level: Optional[str]
    if hard or len(severe) >= 2:
        level = "CRITICAL"
    elif severe:
        level = "HIGH"
    elif len(elevated) >= 3:
        level = "HIGH"
    elif elevated:
        level = "MEDIUM"
    elif financial or len(solvency) < MIN_SOLVENCY_MODELS:
        level = None
    else:
        level = "LOW"
    if level is None:
        status = "NOT_APPLICABLE" if financial else "INSUFFICIENT_DATA"
        reasons.append(na if financial else f"fewer than {MIN_SOLVENCY_MODELS} solvency models (Altman, Ohlson, Zmijewski) have their inputs; no level is given")
    else:
        status = "OK" if financial or len(solvency) >= MIN_SOLVENCY_MODELS else "PARTIAL"
        if level == "LOW":
            reasons.append("no model flags the company")
    return {"agent": "risk", "version": VERSION, "advisoryOnly": True, "level": level, "status": status, "reasons": reasons,
            "hardReasons": hard, "signals": signals,
            "dataSufficiency": {"solvencyModelsAvailable": len(solvency), "required": MIN_SOLVENCY_MODELS,
                                "missing": {s["id"]: s["missing"] for s in signals if s["missing"] and s["applicable"]}},
            "decisionLogicVersion": decision_logic.logic_version(),
            "asOf": {"filingPeriodEnd": company.filing_period_end, "priceObservedAt": company.price_observed_at},
            "disclaimer": "Research aid on stored statements and prices. Not a credit rating, not a forecast and not investment advice; "
                          "it does not change any BIAP score, tier or call."}
