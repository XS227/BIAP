"""EODHD fundamentals adapter (statements + highlights) for BIAP Global: PREPARED, OFF by default.

Feature flag ``BIAP_EODHD_FUNDAMENTALS=1`` and a token in ``BIAP_EODHD_API_TOKEN`` are both required; with either missing every call
raises ``GlobalProviderError("disabled")`` and nothing is requested. The adapter does NOT feed the Evidence gate yet: official filings stay the
source of truth (display licence for third-party fundamentals is unresolved, see docs/DATA_VENDOR_OPTIONS.md). It exists so a one-week
trial can measure statement completeness per market (``tools/eodhd_trial.py``) and so a later decision is a switch, not a project.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from .analysis_ledger import financial_completeness
from .providers import GlobalProviderError

FLAG = "BIAP_EODHD_FUNDAMENTALS"
TOKEN_ENV = "BIAP_EODHD_API_TOKEN"
# BIAP exchange -> EODHD exchange code
EODHD_EXCHANGE = {"XETRA": "XETRA", "FRANKFURT": "F", "BME_MADRID": "MC", "EURONEXT_PARIS": "PA", "EURONEXT_AMSTERDAM": "AS", "EURONEXT_MILAN": "MI",
                  "NASDAQ_STOCKHOLM": "ST", "EURONEXT_OSLO": "OL", "NASDAQ_HELSINKI": "HE", "LSE": "LSE", "NASDAQ": "US", "NYSE": "US"}


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on") and bool(os.environ.get(TOKEN_ENV, "").strip())


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _latest(section: Optional[dict], period: str = "yearly") -> dict:
    rows = (section or {}).get(period) or {}
    if not isinstance(rows, dict) or not rows:
        return {}
    return rows[max(rows)]  # keys are period-end dates (ISO), newest = max


def to_company_fields(payload: dict) -> dict:
    """Map an EODHD /fundamentals payload to the field names BIAP's completeness check uses. Missing stays None (never filled)."""
    fin = (payload or {}).get("Financials") or {}
    inc, bal, cf = _latest(fin.get("Income_Statement")), _latest(fin.get("Balance_Sheet")), _latest(fin.get("Cash_Flow"))
    hi, val, gen = (payload or {}).get("Highlights") or {}, (payload or {}).get("Valuation") or {}, (payload or {}).get("General") or {}
    debt = _num(bal.get("shortLongTermDebtTotal")) or _num(bal.get("totalDebt"))
    if debt is None:
        parts = [_num(bal.get("shortTermDebt")), _num(bal.get("longTermDebt"))]
        debt = sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None
    cfo, capex = _num(cf.get("totalCashFromOperatingActivities")), _num(cf.get("capitalExpenditures"))
    fields = {
        "revenue": _num(inc.get("totalRevenue")), "operating_income": _num(inc.get("operatingIncome")), "net_income": _num(inc.get("netIncome")),
        "ebitda": _num(inc.get("ebitda")) or _num(hi.get("EBITDA")), "total_assets": _num(bal.get("totalAssets")),
        "total_equity": _num(bal.get("totalStockholderEquity")), "total_debt": debt, "interest_expense": _num(inc.get("interestExpense")),
        "operating_cash_flow": cfo, "free_cash_flow": _num(cf.get("freeCashFlow")) if _num(cf.get("freeCashFlow")) is not None else (cfo - abs(capex) if cfo is not None and capex is not None else None),
        "market_cap": _num(hi.get("MarketCapitalization")), "pe": _num(hi.get("PERatio")) or _num(val.get("TrailingPE")), "ev_ebitda": _num(val.get("EnterpriseValueEbitda")),
        "sector": gen.get("Sector") or None, "currency": gen.get("CurrencyCode") or None,
        "statement_period_end": max((fin.get("Income_Statement") or {}).get("yearly") or {"": 0}) or None,
    }
    return fields


def completeness_of(payload: dict) -> dict:
    """Same tiers as the ledger: ``coveragePct``, ``coreComplete``, ``valuationComplete``, ``missing``."""
    return financial_completeness({"company": to_company_fields(payload)})


def fetch_fundamentals(ticker: str, exchange: str, *, client: Optional[httpx.Client] = None, timeout: float = 45.0) -> dict:
    if not enabled():
        raise GlobalProviderError(f"EODHD fundamentals disabled ({FLAG}=0 or {TOKEN_ENV} missing)")
    code = EODHD_EXCHANGE.get(exchange.upper())
    if not code:
        raise GlobalProviderError(f"no EODHD exchange code for {exchange}")
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        r = client.get(f"https://eodhd.com/api/fundamentals/{ticker}.{code}", params={"api_token": os.environ[TOKEN_ENV].strip(), "fmt": "json"})
        if r.status_code in (402, 403):
            raise GlobalProviderError(f"EODHD refused the request (HTTP {r.status_code}): plan does not include fundamentals for this exchange")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise GlobalProviderError(f"EODHD fundamentals request failed: {type(exc).__name__}") from exc
    finally:
        if own:
            client.close()
