"""Inputs for the Risk Agent that are not company fields: thresholds (config), the US GDP deflator, statement-date FX and the
statement unit scale. Everything here is read-only and never guesses: a missing value is reported, not defaulted."""
from __future__ import annotations

import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional

from .models import GlobalCompany

_DATA = Path(__file__).resolve().parent / "data"
CONFIG_PATH = _DATA / "risk_agent_config.json"
DEFLATOR_PATH = _DATA / "us_gdp_deflator_gdpdef.json"
CONFIG_ENV = "RISK_AGENT_CONFIG"

_REQUIRED_THRESHOLDS = ("altman_safe", "altman_distress", "zmijewski_severe", "zmijewski_elevated", "ohlson_severe", "ohlson_elevated",
                        "beneish", "volatility_elevated_pct", "drawdown_elevated_pct", "interest_coverage_elevated",
                        "interest_coverage_severe")


# --- config ---------------------------------------------------------------------------------------------------------------
def load_config(path: Optional[Path] = None) -> dict:
    p = Path(path or os.environ.get(CONFIG_ENV) or CONFIG_PATH)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    th = cfg.get("thresholds") or {}
    missing = [k for k in _REQUIRED_THRESHOLDS if not isinstance(th.get(k), (int, float)) or isinstance(th.get(k), bool) or not math.isfinite(th[k])]
    if missing:
        raise ValueError(f"risk agent config {p} is missing numeric thresholds: {missing}")
    if not th["ohlson_severe"] >= th["ohlson_elevated"] or not th["zmijewski_severe"] >= th["zmijewski_elevated"] \
            or not th["altman_safe"] >= th["altman_distress"] or not th["interest_coverage_elevated"] >= th["interest_coverage_severe"]:
        raise ValueError(f"risk agent config {p}: severe/elevated thresholds are in the wrong order")
    cfg.setdefault("rules", {})
    cfg["rules"].setdefault("min_solvency_models", 2)
    cfg["rules"].setdefault("elevated_signals_for_high", 3)
    cfg.setdefault("unit_scale", {})
    cfg["unit_scale"].setdefault("plausibility_assets_to_market_cap_min", 0.003)
    cfg["unit_scale"].setdefault("plausibility_assets_to_market_cap_max", 300.0)
    cfg.setdefault("ohlson", {})
    cfg["ohlson"].setdefault("asset_unit_usd", 1.0)
    cfg.setdefault("leases", {})
    cfg["leases"].setdefault("ifrs16_non_us", True)
    cfg["_path"] = str(p)
    return cfg


# --- US GDP implicit price deflator (FRED GDPDEF), 1968 = 100 ----------------------------------------------------------------
_DEFLATOR: Optional[dict] = None


def deflator_data() -> dict:
    global _DEFLATOR
    if _DEFLATOR is None:
        _DEFLATOR = json.loads(DEFLATOR_PATH.read_text(encoding="utf-8"))
    return _DEFLATOR


def deflator_index(year: int) -> Optional[dict]:
    """Price index (1968 = 100) for a calendar/fiscal year; ``None`` when the year is not in the data file. A year with fewer than four
    quarters (the current year) is returned with ``partial=True`` so the caller can see it."""
    data = deflator_data()
    row = (data.get("years") or {}).get(str(int(year)))
    if not row:
        return None
    return {"index": float(row["index_1968_100"]), "year": int(year), "partial": int(row.get("quarters", 4)) < 4,
            "series": data.get("fred_series"), "dataVersion": data.get("version"), "sourceSha256": data.get("source_csv_sha256")}


# --- statement-date FX --------------------------------------------------------------------------------------------------------
def statement_fx(company: GlobalCompany, provider: Any = None) -> dict:
    """Reporting currency -> USD at the ECB reference fixing on/before the statement (balance-sheet) date. Never the live rate."""
    currency = str(company.reporting_currency or "").upper()
    if not currency:
        return {"ok": False, "reason": "reporting currency unknown"}
    if not company.filing_period_end:
        return {"ok": False, "reason": "statement date unknown", "currency": currency}
    try:
        on = date.fromisoformat(str(company.filing_period_end)[:10])
    except ValueError:
        return {"ok": False, "reason": f"statement date {company.filing_period_end!r} is not an ISO date", "currency": currency}
    if currency == "USD":
        return {"ok": True, "currency": "USD", "rate": 1.0, "rateDate": on.isoformat(), "requestedDate": on.isoformat(), "provider": "identity"}
    try:
        if provider is None:
            from .fx_history import default_provider
            provider = default_provider()
        q = provider.rate(currency, "USD", on)
    except Exception as exc:                          # missing cache, no fixing within the gap, unsupported currency
        return {"ok": False, "reason": f"statement-date FX unavailable: {str(exc)[:160]}", "currency": currency, "requestedDate": on.isoformat()}
    return {"ok": True, "currency": currency, "rate": q.rate, "rateDate": q.rate_date, "requestedDate": q.requested, "provider": q.provider}


# --- statement unit scale -----------------------------------------------------------------------------------------------------
# Provider -> why its statement values are already in FULL currency units (verified in the adapter code or the data format, 2026-11-25):
_FULL_UNIT_PROVIDERS = (
    ("sec-edgar", "SEC companyfacts XBRL: absolute values in the unit named by the fact (USD)"),
    ("esef-xbrl", "ESEF xBRL-JSON (OIM): canonical absolute values, iXBRL scale already applied"),
    ("official-oam-", "OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values"),
    ("de-reviewed-issuer-annual-report", "curated reviewed file de_verified_annual_reports.json: full currency units (e.g. Mercedes-Benz total assets 255 466 000 000)"),
    ("cvm", "CVM adapter multiplies by ESCALA_MOEDA (MIL / MILHAO) in cvm._scaled_value"),
    ("dfm", "DFM adapter multiplies by the statement scale in dfm_fundamentals._statement_scale"),
    ("adx", "ADX adapter multiplies K/M/B/T suffixes in adx_fundamentals._scaled_number"),
    ("hkex", "HKEX adapter multiplies HKD millions in hkex_issuer (_HKD_MILLION)"),
    ("edinet", "EDINET XBRL: absolute values"),
)


def statement_scale(company: GlobalCompany, cfg: Optional[Mapping] = None) -> dict:
    """Is the statement in full currency units?  status: VERIFIED (adapter/format guarantees full units), INFERRED (provider not
    verified, but total assets vs market cap in the same currency is plausible), SUSPECT (implausible ratio: possible thousands/
    millions error), UNKNOWN (cannot tell).  Only VERIFIED and INFERRED allow the scale-dependent Ohlson SIZE term."""
    cfg = cfg or load_config()
    providers = sorted({(s.provider or "").lower() for s in company.sources
                        if any(t in (s.source_type or "") for t in ("financial_statement", "xbrl", "fundamental", "financial_metrics"))})
    for prefix, why in _FULL_UNIT_PROVIDERS:
        if any(p.startswith(prefix) or prefix in p for p in providers):
            return {"status": "VERIFIED", "factor": 1.0, "providers": providers, "basis": why, "flags": []}
    ta, mcap = company.total_assets, company.market_cap
    same_ccy = company.reporting_currency and company.currency and str(company.reporting_currency).upper() == str(company.currency).upper()
    if not ta or ta <= 0 or not mcap or mcap <= 0 or not same_ccy:
        return {"status": "UNKNOWN", "factor": None, "providers": providers, "basis": "provider not verified and no same-currency market cap to cross-check",
                "flags": ["statement unit scale unknown"]}
    ratio = float(ta) / float(mcap)
    lo, hi = cfg["unit_scale"]["plausibility_assets_to_market_cap_min"], cfg["unit_scale"]["plausibility_assets_to_market_cap_max"]
    if lo <= ratio <= hi:
        return {"status": "INFERRED", "factor": 1.0, "providers": providers, "assetsToMarketCap": ratio,
                "basis": f"provider not verified; total assets / market cap = {ratio:.2f} is inside [{lo}, {hi}]", "flags": ["statement unit scale inferred, not verified"]}
    return {"status": "SUSPECT", "factor": None, "providers": providers, "assetsToMarketCap": ratio,
            "basis": f"total assets / market cap = {ratio:.4g} is outside [{lo}, {hi}]: the statement may be in thousands/millions",
            "flags": ["statement unit scale suspect"]}
