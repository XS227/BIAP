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
from datetime import datetime, timezone
import time
from typing import Any, Callable, Iterable, Optional

from codal_inbox import symbol_key as _base_symbol_key

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def symbol_key(value: Any) -> str:
    """Lookup key: letter forms / ZWNJ / spaces folded (codal_inbox) and Persian/Arabic-Indic digits mapped to ASCII,
    so "شاوان۳", "شاوان٣" and "شاوان3" are the same instrument."""
    return _base_symbol_key(value).translate(_DIGITS)


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


BALANCE_TOLERANCE = 0.01  # genuine statements balance within 0.1%; the loosest balanced stored row is 0.1%
STALE_AFTER_MONTHS = 18
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def period_end(title: Optional[str]) -> Optional[str]:
    """Jalali period end («منتهی به ۱۴۰۴/۱۲/۲۹») from the statement title, ASCII digits, or None."""
    import re as _re
    m = _re.search(r"(\d{4})/(\d{2})/(\d{2})", str(title or "").translate(_FA_DIGITS))
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


def months_old(end: Optional[str], today: Optional["datetime.date"] = None) -> Optional[int]:
    """Whole Jalali months between the statement's period end and today (None when the date is unknown)."""
    if not end:
        return None
    import datetime as _dt
    from codal_data import gregorian_to_jalali
    t = today or _dt.date.today()
    jy, jm, _ = gregorian_to_jalali(t.year, t.month, t.day)
    y, m = int(end[:4]), int(end[5:7])
    return (jy * 12 + jm) - (y * 12 + m)
BALANCE_SHEET_RATIOS = ("roa", "roe", "debt_ratio", "debt_to_equity", "current_ratio", "accruals_ratio", "asset_turnover", "receivable_days")


def _gap(vals: dict) -> Optional[float]:
    ta, tl, te = vals.get("total_assets"), vals.get("total_liabilities"), vals.get("total_equity")
    if None in (ta, tl, te) or not ta:
        return None
    return (ta - tl - te) / abs(ta)


def statement_verification(cur: dict, prev: dict, codal: dict, *, today=None) -> dict:
    """Independent checks on one stored statement. ``unverified`` withholds every balance-sheet ratio built on it.

    verified   - assets = liabilities + equity (±1%) for both periods and no stored re-verification failure
    unverified - the balance sheet does not reconcile, or a re-read of the original filing failed
    incomplete - assets/liabilities/equity are not all present (ratios needing the missing inputs are already withheld)
    """
    checks: dict[str, Any] = {}
    reasons: list[str] = []
    for label, vals in (("current", cur), ("prev", prev)):
        ta0 = vals.get("total_assets")
        if ta0 is not None and ta0 <= 0:  # a balance sheet cannot have zero/negative assets: the gap is not computable, so it is not verified
            reasons.append(f"جمع دارایی‌ها ({'دوره جاری' if label == 'current' else 'دوره قبل'}) صفر یا منفی است؛ ترازنامه قابل تطبیق نیست")
        g = _gap(vals)
        checks[f"balanceGap_{label}"] = None if g is None else round(g, 4)
        if g is not None and abs(g) > BALANCE_TOLERANCE:
            reasons.append(f"ترازنامه ({'دوره جاری' if label == 'current' else 'دوره قبل'}) تراز نیست: دارایی‌ها − (بدهی‌ها + حقوق) = {g:+.1%} از دارایی‌ها")
    ca, ta = cur.get("current_assets"), cur.get("total_assets")
    if ca is not None and ta not in (None, 0) and ca > abs(ta) * 1.001:
        reasons.append("دارایی جاری از جمع دارایی‌ها بیشتر است")
    stored = codal.get("verification") if isinstance(codal.get("verification"), dict) else None
    if stored:
        checks["reparse"] = {k: stored.get(k) for k in ("status", "checkedAt", "method")}
        if stored.get("status") == "unverified" and stored.get("reason") and not reasons:
            reasons.append(f"بازخوانی مستقل صورت مالی اصلی ناموفق بود: {stored['reason']}")
    checks["scope"] = codal.get("report_scope")
    checks["tracingNo"] = codal.get("tracing_no")
    end = period_end(codal.get("report_title"))
    age = months_old(end, today)
    checks["periodEnd"], checks["monthsOld"] = end, age
    stale = age is not None and age > STALE_AFTER_MONTHS
    if stale:
        checks["stale"] = True
    tracing = codal.get("tracing_no")
    if tracing:
        reasons = [f"{r} • شماره رهگیری کدال {tracing}" for r in reasons]
    if reasons:
        return {"status": "unverified", "reasons": reasons, "checks": checks, "stale": stale}
    have_all = all(cur.get(k) is not None for k in ("total_assets", "total_liabilities", "total_equity"))
    notes = [] if have_all else ["جمع دارایی/بدهی/حقوق کامل نیست؛ تطبیق ترازنامه ممکن نیست"]
    if stale:
        notes.append(f"صورت مالی مربوط به دوره‌ی منتهی به {end} است ({age} ماه پیش)؛ جاری نیست و در آمار مقایسه‌ای نمی‌آید")
    return {"status": "verified" if have_all else "incomplete", "reasons": notes, "checks": checks, "stale": stale}


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
    verification = statement_verification(cur, prev, codal)
    return {
        "present": any(v is not None for v in cur.values()), "periodEnd": period_end(title),
        "current": cur, "prev": prev, "scope": codal.get("report_scope"), "tracingNo": codal.get("tracing_no"),
        "title": title or None, "periodType": period_type, "auditStatus": "unaudited" if is_unaudited_title(title) else "audited",
        "auditOpinion": None if is_unaudited_title(title) else codal.get("audit_opinion"),
        "auditorName": codal.get("auditor_name"), "auditBasis": codal.get("audit_basis"),
        "source": codal.get("source") or "CODAL", "reportUrl": codal.get("report_url"), "verification": verification,
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
    unverified = (view.get("verification") or {}).get("status") == "unverified"
    for key, label, formula, value, inputs in specs:
        if unverified and key in BALANCE_SHEET_RATIOS and value is not None:
            out[key] = {"label": label, "formula": formula, "value": None, "inputs": inputs, "missing": [], "unverified": True,
                        "reason": "تأییدنشده: ترازنامه‌ی ذخیره‌شده با صورت مالی اصلی هم‌خوان نیست؛ عدد منتشر نمی‌شود" + (f" • شماره رهگیری کدال {view.get('tracingNo')}" if view.get("tracingNo") else ""),
                        "withheldValue": None}
            continue
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


def is_unaudited_title(title: Optional[str]) -> bool:
    """CODAL marks unaudited statements «(حسابرسی نشده)» in the title: such a statement has no auditor opinion."""
    t = str(title or "").translate(str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " ", "\u00a0": " "}))
    return "حسابرسی نشده" in " ".join(t.split())


HISTORY_PRICE_MAX_AGE_DAYS = 5


def price_from_recent_history(market: dict, hist: list[dict], now_iso: Optional[str] = None) -> tuple[dict, Optional[str]]:
    """When the stored quote is empty but BIAP recorded a recent daily close (price, P/E, market cap, change%), use that
    recorded observation - labelled with its date (``priceSource = history:<date>``) - instead of reporting the company as
    having no market data at all. Never invents a value: only fields present on the recorded row are copied."""
    if market.get("price") or not hist:
        return market, None
    # Multiple sources can record the same trading date. The list returned by
    # market_memory is ordered by observed_at, but max(date) alone picked the
    # FIRST (oldest) row on ties. Choose the latest recording timestamp and
    # preserve input order as a deterministic fallback for legacy rows.
    last = max(enumerate(hist), key=lambda pair: (
        str(pair[1].get("observed_date") or ""),
        str(pair[1].get("observed_at") or ""),
        pair[0],
    ))[1]
    day = str(last.get("observed_date") or "")[:10]
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
        today = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).date() if now_iso else datetime.now(timezone.utc).date()
    except (ValueError, AttributeError):
        return market, None
    if not 0 <= (today - d).days <= HISTORY_PRICE_MAX_AGE_DAYS:
        return market, None
    out = dict(market)
    for field, key in (("price", "price"), ("pe", "pe"), ("market_cap", "market_cap"), ("change_percent", "change_percent")):
        v = num(last.get(key))
        if v is not None and out.get(field) is None:
            out[field] = v
    out["price"] = num(last.get("price"))
    return out, day


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
    ver = view.get("verification") or {}
    if ver.get("status") == "unverified":
        warnings.append("balance sheet does not balance within 1% or failed re-verification: balance-sheet ratios are withheld (unverified)")
    if not market.get("price"):
        warnings.append("no market price on record")
    return {"missing": missing, "warnings": warnings, "historyObservations": history_n}


RATE_LIMIT_MARKERS = ("429", "rate limit", "rate-limit", "too many requests", "retry-after")


def data_status(item: dict, market: dict, view: dict, history_n: int) -> dict:
    """Why a module may be empty: explicit, machine-readable reasons instead of a generic empty result."""
    has_price = bool(market.get("price"))
    has_codal = bool(view.get("present"))
    codes: list[str] = []
    if not has_price and not has_codal and history_n == 0:
        codes.append("REGISTERED_ONLY")
    else:
        if not has_price:
            codes.append("MISSING_MARKET")
        if not has_codal:
            codes.append("MISSING_CODAL")
    err = str(item.get("lastError") or item.get("last_error") or "").lower()
    if err and any(m in err for m in RATE_LIMIT_MARKERS) and (not has_price or not has_codal):
        codes.append("SOURCE_RATE_LIMITED")
    return {"codes": codes, "hasCurrentPrice": has_price, "hasCodal": has_codal, "historyObservations": history_n,
            "hasHistory": history_n > 0, "inStore": not bool(item.get("registryOnly")), "lastError": item.get("lastError") or item.get("last_error")}


def build_company_dataset(item: dict, history: Iterable[dict] = (), *, now_iso: Optional[str] = None) -> dict:
    """``item`` is a ListedCompanyStore row (with ``company``). ``history`` = market-memory daily snapshots."""
    company = item.get("company") or {}
    codal = company.get("codal") if isinstance(company.get("codal"), dict) else None
    market = clean_market(company.get("market"))
    view = fundamentals_view(codal)
    hist = [h for h in history if num(h.get("price")) is not None]
    market, price_from_history = price_from_recent_history(market, hist, now_iso)
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
            "baselineEnrichedAt": item.get("enrichedAt"), "priceSource": (f"history:{price_from_history}" if price_from_history else (company.get("market") or {}).get("price_source")),
            "financialSource": view.get("source") if view["present"] else None, "tracingNo": view.get("tracingNo"),
            "statementTitle": view.get("title"), "statementScope": view.get("scope"), "periodType": view.get("periodType"),
            "verification": view.get("verification"), "auditOpinionSource": "codal_filing" if view.get("auditOpinion") else None,
            "dataAvailability": company.get("data_available") or {},
        },
        "quality": {**data_quality(company, view, market, len(hist)), **({"priceFromHistory": price_from_history} if price_from_history else {})},
        "status": data_status(item, market, view, len(hist)),
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
        "stale": 1 if (v.get("verification") or {}).get("stale") else 0, "verification": (v.get("verification") or {}).get("status"),
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


class _Registry:
    def __init__(self) -> None:
        self.primary: Optional[set] = None
        self.primary_keys: set = set()
        self.category: dict = {}
        self.issuer: dict = {}
        self.symbol: dict = {}
        self.category_by_key: dict = {}
        self.issuer_by_key: dict = {}
        self.aliases: dict = {}
        self.companies: list = []


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
            conn = sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True, timeout=30)
            try:
                conn.row_factory = sqlite3.Row
                reg = self._registry(conn)
                seen_keys: set[str] = set()
                for r in conn.execute("SELECT code,symbol,name_fa,market,enriched_at,last_error,company_json FROM listed_companies"):
                    try:
                        company = json.loads(r["company_json"]) if r["company_json"] else None
                    except (TypeError, ValueError):
                        company = None
                    row = universe_row({"code": r["code"], "symbol": r["symbol"], "name": r["name_fa"], "market": r["market"],
                                        "enrichedAt": r["enriched_at"], "company": company})
                    ckey = symbol_key(r["code"])
                    seen_keys.add(ckey)
                    if str(row["symbol"] or "").isdigit() and reg.symbol.get(r["code"]):
                        # some rows were stored with the instrument code in the symbol column: the registry knows the real symbol
                        row["symbol"] = reg.symbol[r["code"]]
                        row["symbol_key"] = symbol_key(row["symbol"])
                    # registry codes may differ from stored codes only by spelling (ZWNJ / Arabic letters): match on the folded key
                    row["is_primary"] = 1 if (reg.primary is None or r["code"] in reg.primary or ckey in reg.primary_keys) else 0
                    row["category"] = reg.category.get(r["code"]) or reg.category_by_key.get(ckey)
                    row["issuer_id"] = reg.issuer.get(r["code"]) or reg.issuer_by_key.get(ckey)
                    row["last_error"] = r["last_error"]
                    row["registry_only"] = 0
                    built.append(row)
                # the registry is the canonical discovery source: primary companies without a stored row keep their identity
                for company in reg.companies:
                    if symbol_key(company["code"]) in seen_keys:
                        continue
                    row = universe_row({"code": company["code"], "symbol": company["symbol"], "name": company["name"],
                                        "market": company["market"], "enrichedAt": None, "company": None})
                    row.update({"is_primary": 1, "category": company["category"], "issuer_id": company["issuer_id"],
                                "last_error": None, "registry_only": 1})
                    built.append(row)
                for row in built:
                    keys = {symbol_key(row["symbol"]), symbol_key(row["name"])}
                    keys |= reg.aliases.get(row.get("issuer_id") or "", set())
                    row["aliases"] = sorted(k for k in keys if k)
                    row["name_key"] = symbol_key(row["name"])
            finally:
                conn.close()
            self._rows, self._built_at, self._stamp = built, clock(), stamp
            return built

    @staticmethod
    def _registry(conn) -> "_Registry":
        """Genuine primary-company codes (one per issuer, shares only), each instrument's category/issuer and name aliases.

        ``primary=None`` means the DB has no registry yet (every stored row is then treated as primary).
        """
        reg = _Registry()
        try:
            from company_registry_store import COMPANY_CATEGORIES
            marks = ",".join("?" for _ in COMPANY_CATEGORIES)
            companies = conn.execute(
                f"SELECT issuer_id,canonical_symbol,canonical_name,category,primary_instrument_code FROM company_registry WHERE category IN ({marks})",
                tuple(COMPANY_CATEGORIES)).fetchall()
            inst = conn.execute("SELECT code,symbol,name,market,category,issuer_id FROM instrument_registry").fetchall()
        except sqlite3.Error:
            return reg
        by_code = {str(i["code"]): i for i in inst}
        for i in inst:
            code = str(i["code"])
            reg.category[code] = i["category"]; reg.issuer[code] = i["issuer_id"]; reg.symbol[code] = i["symbol"]
            k = symbol_key(code)
            reg.category_by_key.setdefault(k, i["category"]); reg.issuer_by_key.setdefault(k, i["issuer_id"])
            if i["issuer_id"]:
                reg.aliases.setdefault(i["issuer_id"], set()).update({symbol_key(i["symbol"]), symbol_key(i["name"])} - {""})
        prim = set()
        for c in companies:
            code = str(c["primary_instrument_code"])
            prim.add(code); reg.primary_keys.add(symbol_key(code))
            i = by_code.get(code)
            reg.aliases.setdefault(c["issuer_id"], set()).update({symbol_key(c["canonical_symbol"]), symbol_key(c["canonical_name"])} - {""})
            reg.companies.append({"code": code, "symbol": c["canonical_symbol"], "name": c["canonical_name"] or c["canonical_symbol"],
                                  "market": (i["market"] if i else None), "category": c["category"], "issuer_id": c["issuer_id"]})
        reg.primary = prim or None
        return reg

    @staticmethod
    def _db_stamp(store) -> Any:
        try:
            conn = sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True, timeout=30)
            try:
                listed = conn.execute("SELECT COUNT(*), MAX(updated_at) FROM listed_companies").fetchone()
                try:
                    reg = conn.execute("SELECT COUNT(*), MAX(last_seen_at) FROM company_registry").fetchone()
                except sqlite3.Error:
                    reg = None
                return (tuple(listed), tuple(reg) if reg else None)
            finally:
                conn.close()
        except sqlite3.Error:
            return None


UNIVERSE = UniverseCache()
