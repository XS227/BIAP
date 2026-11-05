"""Normalized, provenance-carrying datasets for every listed company (shared by all Iran modules).

One code path for every company: resolve -> market + CODAL observations -> ratios -> data tier.
Nothing here knows a particular symbol. Missing inputs stay missing (``None``) and are listed
explicitly; no value is estimated or borrowed from another company.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from typing import Any, Callable, Iterable, Optional

from codal_inbox import symbol_key

# ---- field maps ------------------------------------------------------------------------------

FUNDAMENTAL_FIELDS = {
    "revenue": "revenue", "net_profit": "net_profit", "operating_profit": "operating_profit",
    "gross_profit": "gross_profit", "total_assets": "total_assets", "total_equity": "total_equity",
    "total_liabilities": "total_liabilities", "current_assets": "current_assets",
    "current_liabilities": "current_liabilities", "receivables": "receivables",
    "retained_earnings": "retained_earnings", "fixed_assets": "fixed_assets",
    "depreciation": "depreciation", "sga_expense": "sga_expense",
}
# CODAL JSON stores most items as <name>_current / <name>_prev; operating cash flow is the same.
CFO_KEY = "operating_cash_flow"

MARKET_FIELDS = ("last_price", "closing_price", "price", "yesterday_price", "change_percent", "pe", "eps_value",
                 "market_cap", "volume_today", "trade_value_today", "trade_count_today", "avg_volume_30d",
                 "price_52w_high", "price_52w_low", "shares_outstanding", "sector_name", "sector_code",
                 "sector_avg_pe", "market_title")

TIER_FULL = "full"
TIER_PARTIAL = "partial_financials"
TIER_MARKET = "market_only"
TIER_REGISTERED = "registered_only"

CORE_FINANCIALS = ("revenue", "net_profit", "total_assets", "total_equity", "total_liabilities")


def num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _fundamental_pair(codal: dict, name: str) -> tuple[Optional[float], Optional[float]]:
    return num(codal.get(f"{name}_current")), num(codal.get(f"{name}_prev"))


def fundamentals_view(codal: Optional[dict]) -> dict:
    """Current/previous statement values by short name, plus statement identity."""
    if not isinstance(codal, dict) or not codal:
        return {"current": {}, "prev": {}, "present": False}
    cur: dict[str, Optional[float]] = {}
    prev: dict[str, Optional[float]] = {}
    for short, stem in list(FUNDAMENTAL_FIELDS.items()) + [("operating_cash_flow", CFO_KEY)]:
        cur[short], prev[short] = _fundamental_pair(codal, stem)
    title = str(codal.get("report_title") or "")
    period_type = "interim" if ("میان" in title and "دوره" in title) else ("annual" if "سال مالی" in title else "unknown")
    return {
        "present": any(v is not None for v in cur.values()),
        "current": cur, "prev": prev, "scope": codal.get("report_scope"), "tracingNo": codal.get("tracing_no"),
        "title": title or None, "periodType": period_type, "auditOpinion": codal.get("audit_opinion"),
        "source": codal.get("source") or "CODAL", "reportUrl": codal.get("report_url"),
    }


def _div(a: Optional[float], b: Optional[float], *, positive_den: bool = False) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    if positive_den and b < 0:
        return None
    return a / b


def _growth(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def compute_ratios(view: dict) -> dict[str, dict]:
    """Every ratio with its formula and inputs; ``value`` is None (with a reason) when inputs are missing."""
    c, p = view.get("current") or {}, view.get("prev") or {}
    annual = view.get("periodType") == "annual"
    specs: list[tuple[str, str, str, Optional[float], list[str]]] = []

    def add(key: str, label: str, formula: str, value: Optional[float], inputs: list[str]) -> None:
        specs.append((key, label, formula, value, inputs))

    add("gross_margin", "حاشیه سود ناخالص", "سود ناخالص ÷ درآمد", _div(c.get("gross_profit"), c.get("revenue")), ["gross_profit", "revenue"])
    add("operating_margin", "حاشیه سود عملیاتی", "سود عملیاتی ÷ درآمد", _div(c.get("operating_profit"), c.get("revenue")), ["operating_profit", "revenue"])
    add("net_margin", "حاشیه سود خالص", "سود خالص ÷ درآمد", _div(c.get("net_profit"), c.get("revenue")), ["net_profit", "revenue"])
    add("roa", "بازده دارایی‌ها (ROA)", "سود خالص ÷ جمع دارایی‌ها", _div(c.get("net_profit"), c.get("total_assets"), positive_den=True), ["net_profit", "total_assets"])
    add("roe", "بازده حقوق صاحبان سهام (ROE)", "سود خالص ÷ حقوق صاحبان سهام (فقط حقوق مثبت)", _div(c.get("net_profit"), c.get("total_equity"), positive_den=True), ["net_profit", "total_equity"])
    add("debt_ratio", "نسبت بدهی", "جمع بدهی‌ها ÷ جمع دارایی‌ها", _div(c.get("total_liabilities"), c.get("total_assets"), positive_den=True), ["total_liabilities", "total_assets"])
    add("debt_to_equity", "بدهی به حقوق صاحبان سهام", "جمع بدهی‌ها ÷ حقوق صاحبان سهام (فقط حقوق مثبت)", _div(c.get("total_liabilities"), c.get("total_equity"), positive_den=True), ["total_liabilities", "total_equity"])
    add("current_ratio", "نسبت جاری", "دارایی جاری ÷ بدهی جاری", _div(c.get("current_assets"), c.get("current_liabilities"), positive_den=True), ["current_assets", "current_liabilities"])
    add("revenue_growth", "رشد درآمد", "(درآمد دوره − درآمد دوره قبل) ÷ |درآمد دوره قبل|", _growth(c.get("revenue"), p.get("revenue")), ["revenue", "revenue_prev"])
    add("profit_growth", "رشد سود خالص", "(سود دوره − سود دوره قبل) ÷ |سود دوره قبل|", _growth(c.get("net_profit"), p.get("net_profit")), ["net_profit", "net_profit_prev"])
    add("cfo_to_profit", "کیفیت سود (جریان نقد عملیاتی ÷ سود)", "جریان نقد عملیاتی ÷ سود خالص (فقط سود مثبت)", _div(c.get("operating_cash_flow"), c.get("net_profit"), positive_den=True), ["operating_cash_flow", "net_profit"])
    accruals = None
    if None not in (c.get("net_profit"), c.get("operating_cash_flow")) and c.get("total_assets") not in (None, 0):
        accruals = (c["net_profit"] - c["operating_cash_flow"]) / abs(c["total_assets"])
    add("accruals_ratio", "اقلام تعهدی به دارایی", "(سود خالص − جریان نقد عملیاتی) ÷ جمع دارایی‌ها", accruals, ["net_profit", "operating_cash_flow", "total_assets"])
    add("asset_turnover", "گردش دارایی‌ها", "درآمد ÷ جمع دارایی‌ها (فقط گزارش سالانه)", _div(c.get("revenue"), c.get("total_assets"), positive_den=True) if annual else None, ["revenue", "total_assets"])
    rec_days = _div(c.get("receivables"), c.get("revenue"), positive_den=True)
    add("receivable_days", "روز وصول مطالبات", "مطالبات ÷ درآمد × ۳۶۵ (فقط گزارش سالانه)", rec_days * 365 if (annual and rec_days is not None) else None, ["receivables", "revenue"])
    out: dict[str, dict] = {}
    for key, label, formula, value, inputs in specs:
        entry: dict[str, Any] = {"label": label, "formula": formula, "value": value, "inputs": inputs}
        if value is None:
            missing = []
            for name in inputs:
                src = p if name.endswith("_prev") else c
                field = name[:-5] if name.endswith("_prev") else name
                if src.get(field) is None:
                    missing.append(name)
            entry["missing"] = missing
            if not missing:
                entry["reason"] = "denominator is zero/negative or period type is not annual"
        out[key] = entry
    return out


def classify_tier(market: dict, view: dict) -> str:
    cur = view.get("current") or {}
    if view.get("present") and all(cur.get(k) is not None for k in CORE_FINANCIALS):
        return TIER_FULL if cur.get("operating_cash_flow") is not None else TIER_PARTIAL
    if view.get("present"):
        return TIER_PARTIAL
    if any(num(market.get(k)) is not None for k in ("last_price", "closing_price", "price")):
        return TIER_MARKET
    return TIER_REGISTERED


def clean_market(market: Optional[dict]) -> dict:
    market = market if isinstance(market, dict) else {}
    out = {k: market.get(k) for k in MARKET_FIELDS if market.get(k) is not None}
    out["price"] = num(market.get("last_price") or market.get("closing_price") or market.get("price"))
    return out


def data_quality(company: dict, view: dict, market: dict, history_n: int) -> dict:
    warnings: list[str] = []
    missing: list[str] = []
    cur = view.get("current") or {}
    for key in CORE_FINANCIALS:
        if view.get("present") and cur.get(key) is None:
            missing.append(key)
    if view.get("present") and cur.get("operating_cash_flow") is None:
        missing.append("operating_cash_flow")
    if view.get("periodType") == "interim":
        warnings.append("interim statement: annual-only ratios are withheld")
    if view.get("present") and not view.get("scope"):
        warnings.append("statement scope (consolidated/standalone) not recorded")
    if cur.get("total_assets") is not None and cur.get("total_liabilities") is not None and cur.get("total_equity") is not None:
        ta, tl, te = cur["total_assets"], cur["total_liabilities"], cur["total_equity"]
        if ta and abs(ta - (tl + te)) / abs(ta) > 0.02:
            warnings.append("balance sheet does not balance within 2%: ratios built on it are unreliable")
    if not market.get("price"):
        warnings.append("no market price on record")
    return {"missing": missing, "warnings": warnings, "historyObservations": history_n}


def build_company_dataset(item: dict, history: Iterable[dict] = (), *, now_iso: Optional[str] = None) -> dict:
    """``item`` is a ListedCompanyStore row (with ``company``). ``history`` = market-memory daily snapshots."""
    company = item.get("company") or {}
    codal = company.get("codal") if isinstance(company.get("codal"), dict) else None
    market = clean_market(company.get("market"))
    view = fundamentals_view(codal)
    hist = [h for h in history if num(h.get("price")) is not None]
    tier = classify_tier(market, view)
    ratios = compute_ratios(view) if view["present"] else {}
    meta = company.get("codal_metadata") or {}
    return {
        "identity": {
            "code": item.get("code"), "symbol": item.get("symbol"), "symbolKey": symbol_key(item.get("symbol")),
            "name": item.get("name"), "market": item.get("market"), "sector": market.get("sector_name"),
            "issuerName": meta.get("company_name") if isinstance(meta, dict) else None,
        },
        "tier": tier,
        "market": market,
        "fundamentals": view,
        "ratios": ratios,
        "history": [{"date": h.get("observed_date"), "price": num(h.get("price")), "changePercent": num(h.get("change_percent")),
                     "pe": num(h.get("pe")), "marketCap": num(h.get("market_cap")), "source": h.get("source")} for h in hist],
        "provenance": {
            "baselineEnrichedAt": item.get("enrichedAt"), "priceSource": (company.get("market") or {}).get("price_source"),
            "financialSource": view.get("source") if view["present"] else None, "tracingNo": view.get("tracingNo"),
            "statementTitle": view.get("title"), "statementScope": view.get("scope"), "periodType": view.get("periodType"),
            "dataAvailability": company.get("data_available") or {},
        },
        "quality": data_quality(company, view, market, len(hist)),
        "generatedAt": now_iso,
    }


# ---- universe table (one flat row per company) ------------------------------------------------

UNIVERSE_RATIO_KEYS = ("gross_margin", "operating_margin", "net_margin", "roa", "roe", "debt_ratio", "debt_to_equity",
                       "current_ratio", "revenue_growth", "profit_growth", "cfo_to_profit", "accruals_ratio",
                       "asset_turnover", "receivable_days")


def universe_row(item: dict) -> dict:
    ds = build_company_dataset(item)
    m, v = ds["market"], ds["fundamentals"]
    cur = v.get("current") or {}
    row: dict[str, Any] = {
        "code": ds["identity"]["code"], "symbol": ds["identity"]["symbol"], "symbol_key": ds["identity"]["symbolKey"],
        "name": ds["identity"]["name"], "market": ds["identity"]["market"], "sector": ds["identity"]["sector"],
        "tier": ds["tier"], "has_market": 1 if m.get("price") is not None else 0, "has_codal": 1 if v.get("present") else 0,
        "scope": v.get("scope"), "period_type": v.get("periodType"), "tracing_no": v.get("tracingNo"),
        "price": m.get("price"), "change_percent": num(m.get("change_percent")), "pe": num(m.get("pe")),
        "eps": num(m.get("eps_value")), "market_cap": num(m.get("market_cap")), "volume": num(m.get("volume_today")),
        "trade_value": num(m.get("trade_value_today")), "enriched_at": item.get("enrichedAt"),
    }
    for key in ("revenue", "net_profit", "operating_profit", "gross_profit", "total_assets", "total_equity",
                "total_liabilities", "current_assets", "current_liabilities", "operating_cash_flow"):
        row[key] = cur.get(key)
    for key in UNIVERSE_RATIO_KEYS:
        row[key] = (ds["ratios"].get(key) or {}).get("value")
    return row


class UniverseCache:
    """Flat universe table, rebuilt when the listed-company DB changes or the TTL passes."""

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._rows: list[dict] = []
        self._built_at = 0.0
        self._stamp: Any = None

    def rows(self, store, *, force: bool = False, clock: Callable[[], float] = time.time) -> list[dict]:
        stamp = self._db_stamp(store)
        with self._lock:
            if not force and self._rows and stamp == self._stamp and clock() - self._built_at < self.ttl:
                return self._rows
            built: list[dict] = []
            with sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True, timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                for r in conn.execute("SELECT code,symbol,name_fa,market,enriched_at,company_json FROM listed_companies"):
                    try:
                        company = json.loads(r["company_json"]) if r["company_json"] else None
                    except (TypeError, ValueError):
                        company = None
                    built.append(universe_row({"code": r["code"], "symbol": r["symbol"], "name": r["name_fa"], "market": r["market"],
                                               "enrichedAt": r["enriched_at"], "company": company}))
            self._rows, self._built_at, self._stamp = built, clock(), stamp
            return built

    @staticmethod
    def _db_stamp(store) -> Any:
        try:
            with sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True, timeout=30) as conn:
                return conn.execute("SELECT COUNT(*), MAX(updated_at) FROM listed_companies").fetchone()
        except sqlite3.Error:
            return None


UNIVERSE = UniverseCache()
