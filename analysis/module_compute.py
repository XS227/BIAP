"""Module computations for listed companies. Every function takes the shared dataset (module_dataset)
and the universe table; none of them knows a specific symbol. A module that cannot be computed returns
status "blocked" with the exact missing inputs, never a placeholder number."""
from __future__ import annotations

import math
from typing import Any, Optional

import module_stats as st
from module_dataset import TIER_FULL, TIER_MARKET, TIER_PARTIAL, TIER_REGISTERED, UNIVERSE_RATIO_KEYS, num

MIN_HISTORY_ANOMALY = 15
MIN_HISTORY_FORECAST = 30
MIN_PEERS = 8

LISTED_MODULES = ("eda", "sql", "kpi-extract", "anomaly", "forecast", "dashboard", "report", "swot", "market-entry",
                  "financial-model", "scenario", "executive-report", "mbr")
PRIVATE_MODULES = ("business-kpi", "governance", "crm", "campaign", "pricing", "plan", "unit", "journey", "voc", "behavior")

# Required inputs per listed-company module (data contract). "any" = at least one of the group.
CONTRACTS: dict[str, dict] = {
    "eda": {"title": "EDA Explorer", "needs": [("universe", "حداقل ۸ شرکت با نسبت‌های مالی در پایگاه BIAP")], "optional": ["history"]},
    "sql": {"title": "SQL / Data Query", "needs": [("universe", "جدول‌های تحلیلی BIAP")]},
    "kpi-extract": {"title": "KPI", "needs_any": ["market.price", "fundamentals"]},
    "anomaly": {"title": "تشخیص ناهنجاری", "needs": [("history>=15", "حداقل ۱۵ مشاهده‌ی قیمت روزانه")]},
    "forecast": {"title": "پیش‌بینی آماری", "needs": [("history>=30", "حداقل ۳۰ مشاهده‌ی قیمت روزانه")]},
    "dashboard": {"title": "BI Dashboard", "needs_any": ["market.price", "fundamentals"]},
    "report": {"title": "گزارش تحلیلی", "needs_any": ["market.price", "fundamentals"]},
    "swot": {"title": "SWOT + رقبا", "needs": [("fundamentals", "صورت مالی CODAL"), ("peers>=8", "حداقل ۸ شرکت هم‌گروه یا بازار برای مقایسه")]},
    "market-entry": {"title": "فرصت و ورود به بازار", "needs": [("sector", "گروه صنعت"), ("peers>=8", "حداقل ۸ شرکت هم‌گروه")]},
    "financial-model": {"title": "Financial Modeling", "needs": [("fundamentals.revenue", "درآمد دوره"), ("fundamentals.net_profit", "سود خالص")]},
    "scenario": {"title": "Scenario Analysis", "needs": [("fundamentals.revenue", "درآمد دوره"), ("fundamentals.net_profit", "سود خالص")]},
    "executive-report": {"title": "گزارش مدیریتی", "needs_any": ["market.price", "fundamentals"]},
    "mbr": {"title": "گزارش MBR", "needs_any": ["market.price", "fundamentals"]},
}


def comparable(universe: list[dict], code: str, *, need_codal: bool = True, same_category: bool = True) -> list[dict]:
    """Genuine primary companies of the same category (banks are not compared with manufacturers)."""
    own = next((r for r in universe if r["code"] == code), None)
    cat = own.get("category") if own else None
    out = [r for r in universe if r.get("is_primary", 1)]
    if need_codal:
        out = [r for r in out if r.get("has_codal")]
    if same_category and cat:
        out = [r for r in out if r.get("category") == cat]
    return out


def fmt_ratio(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 6)


def readiness(ds: dict, peers: int, market_rows: int = 0) -> dict[str, dict]:
    """Per-module readiness for this company: ready / partial / blocked + exact missing inputs."""
    cur = (ds["fundamentals"].get("current") or {})
    has_fund = bool(ds["fundamentals"].get("present"))
    has_price = ds["market"].get("price") is not None
    n_hist = len(ds["history"])
    out: dict[str, dict] = {}
    for key, spec in CONTRACTS.items():
        missing: list[str] = []
        for need, label in spec.get("needs", []):
            ok = {
                "universe": max(peers, market_rows) >= MIN_PEERS, "fundamentals": has_fund,
                "history>=15": n_hist >= MIN_HISTORY_ANOMALY, "history>=30": n_hist >= MIN_HISTORY_FORECAST,
                "peers>=8": peers >= MIN_PEERS, "sector": bool(ds["identity"].get("sector")),
            }.get(need)
            if ok is None and need.startswith("fundamentals."):
                ok = cur.get(need.split(".", 1)[1]) is not None
            if not ok:
                missing.append(label)
        if "needs_any" in spec:
            if not (has_fund or has_price):
                missing.append("قیمت بازار یا صورت مالی")
        if missing:
            status = "blocked"
        elif key in ("kpi-extract", "dashboard", "report", "executive-report", "mbr") and not (has_fund and has_price):
            status = "partial"
            missing = ["صورت مالی CODAL"] if not has_fund else ["قیمت بازار"]
        else:
            status = "ready"
        out[key] = {"title": spec["title"], "status": status, "missing": missing}
    for key in PRIVATE_MODULES:
        out[key] = {"title": key, "status": "needs_private_data", "missing": ["داده‌ی داخلی شرکت (Excel/CSV/اتصال)"]}
    return out


def envelope(module: str, ds: dict, status: str, summary: str, blocks: list[dict], *, missing: Optional[list[str]] = None, note: Optional[str] = None) -> dict:
    return {
        "module": module, "title": CONTRACTS.get(module, {}).get("title", module), "status": status, "summary": summary,
        "blocks": blocks, "missing": missing or [], "note": note, "tier": ds["tier"],
        "provenance": ds["provenance"], "quality": ds["quality"],
        "company": {"code": ds["identity"]["code"], "symbol": ds["identity"]["symbol"], "name": ds["identity"]["name"]},
    }


def blocked(module: str, ds: dict, missing: list[str], why: str) -> dict:
    return envelope(module, ds, "blocked", why, [{"type": "notice", "tone": "warning", "text": why, "missing": missing}], missing=missing)


# ---- KPI -------------------------------------------------------------------------------------

def kpi(ds: dict) -> dict:
    market, view, ratios = ds["market"], ds["fundamentals"], ds["ratios"]
    period = view.get("title")
    items: list[dict] = []

    def add(group, key, label, value, unit, formula, inputs, source, extra_missing=None):
        items.append({"group": group, "key": key, "label": label, "value": fmt_ratio(value), "unit": unit, "formula": formula,
                      "inputs": inputs, "source": source, "period": period if source.startswith("CODAL") else None,
                      "status": "ok" if value is not None else "missing", "missing": extra_missing or []})

    price = market.get("price")
    pe = num(market.get("pe"))
    add("بازار", "price", "قیمت آخر", price, "ریال", "آخرین قیمت معامله/پایانی", ["last_price"], f"بازار ({ds['provenance'].get('priceSource') or 'TSETMC/Tindex'})")
    add("بازار", "change_percent", "تغییر روزانه", num(market.get("change_percent")), "%", "(قیمت − قیمت دیروز) ÷ قیمت دیروز", ["change_percent"], "بازار")
    add("بازار", "pe", "P/E", pe, "×", "قیمت ÷ سود هر سهم (گزارش‌شده توسط منبع)", ["pe"], "بازار")
    add("بازار", "earnings_yield", "بازده سود (۱/PE)", (1 / pe) if pe and pe > 0 else None, "نسبت", "۱ ÷ P/E (فقط P/E مثبت)", ["pe"], "بازار")
    hi, lo = num(market.get("price_52w_high")), num(market.get("price_52w_low"))
    pos = (price - lo) / (hi - lo) if None not in (price, hi, lo) and hi > lo else None
    add("بازار", "range_position", "موقعیت در بازه ۵۲ هفته", pos, "نسبت", "(قیمت − کف) ÷ (سقف − کف)", ["price", "price_52w_high", "price_52w_low"], "بازار")
    vol, avgv = num(market.get("volume_today")), num(market.get("avg_volume_30d"))
    add("بازار", "volume_ratio", "حجم امروز به میانگین ۳۰ روز", (vol / avgv) if vol is not None and avgv else None, "×", "حجم امروز ÷ میانگین حجم ۳۰ روزه", ["volume_today", "avg_volume_30d"], "بازار")
    groups = {"gross_margin": "سودآوری", "operating_margin": "سودآوری", "net_margin": "سودآوری", "roa": "سودآوری", "roe": "سودآوری",
              "revenue_growth": "رشد", "profit_growth": "رشد", "current_ratio": "نقدینگی", "debt_ratio": "بدهی", "debt_to_equity": "بدهی",
              "cfo_to_profit": "جریان نقد", "accruals_ratio": "جریان نقد", "asset_turnover": "کارایی", "receivable_days": "کارایی"}
    for key, group in groups.items():
        r = ratios.get(key)
        if r is None:
            add(group, key, key, None, "نسبت", "—", [], "CODAL", ["صورت مالی CODAL"])
            continue
        unit = "روز" if key == "receivable_days" else ("×" if key in ("current_ratio", "debt_to_equity", "asset_turnover") else "نسبت")
        add(group, key, r["label"], r["value"], unit, r["formula"], r["inputs"], f"CODAL • {view.get('scope') or 'نامشخص'}", r.get("missing"))
    ok = [i for i in items if i["status"] == "ok"]
    missing_inputs = sorted({m for i in items for m in i["missing"]})
    if not ok:
        return blocked("kpi-extract", ds, missing_inputs or ["قیمت بازار", "صورت مالی CODAL"], "هیچ شاخصی با داده‌ی تأییدشده قابل محاسبه نیست.")
    status = "ok" if len(ok) == len(items) else "partial"
    return envelope("kpi-extract", ds, status, f"{len(ok)} از {len(items)} شاخص محاسبه شد؛ هر شاخص فرمول، ورودی و منبع دارد.",
                    [{"type": "kpi_table", "items": items}], missing=missing_inputs,
                    note="مقادیر CODAL فقط از یک صورت مالی با دامنه‌ی مشخص و بدون اختلاط تلفیقی/جداگانه می‌آیند.")


# ---- EDA -------------------------------------------------------------------------------------

EDA_COLUMNS = ["net_margin", "operating_margin", "roa", "roe", "debt_ratio", "current_ratio", "revenue_growth", "profit_growth", "cfo_to_profit",
               "pe", "change_percent", "market_cap", "trade_value"]
EDA_LABELS = {"net_margin": "حاشیه سود خالص", "operating_margin": "حاشیه سود عملیاتی", "roa": "ROA", "roe": "ROE", "debt_ratio": "نسبت بدهی",
              "current_ratio": "نسبت جاری", "revenue_growth": "رشد درآمد", "profit_growth": "رشد سود", "cfo_to_profit": "جریان نقد ÷ سود", "pe": "P/E",
              "change_percent": "تغییر روزانه (٪)", "market_cap": "ارزش بازار", "trade_value": "ارزش معاملات"}
MARKET_COLUMNS = {"pe", "change_percent", "market_cap", "trade_value"}
POSITIVE_ONLY = {"pe", "market_cap", "trade_value"}


def _column_rows(ds: dict, universe: list[dict], col: str, sector_only: bool) -> tuple[list[dict], str]:
    """Rows to describe ``col`` and the scope label. Financial ratios prefer the company's own category;
    when that is too small they widen to every primary company with statements (and say so)."""
    primary = [r for r in universe if r.get("is_primary", 1) and r.get(col) is not None]
    if col in POSITIVE_ONLY:
        primary = [r for r in primary if r[col] > 0]
    code, sector = ds["identity"]["code"], ds["identity"].get("sector")
    own = next((r for r in universe if r["code"] == code), None)
    cat = own.get("category") if own else None
    scopes: list[tuple[list[dict], str]] = []
    if sector_only and sector:
        scopes.append(([r for r in primary if r.get("sector") == sector], f"گروه {sector}"))
    if cat:
        same_cat = [r for r in primary if r.get("category") == cat]
        if len(same_cat) >= 30:  # a same-category sample smaller than this is noisier than the full primary universe
            scopes.append((same_cat, "هم‌دسته"))
    scopes.append((primary, "همه‌ی شرکت‌های اصلی"))
    for rows, label in scopes:
        if len(rows) >= MIN_PEERS:
            return rows, label
    return [], "ناکافی"


def eda(ds: dict, universe: list[dict], *, column: Optional[str] = None, sector_only: bool = False) -> dict:
    primary = [r for r in universe if r.get("is_primary", 1)]
    total = len(primary)
    code = ds["identity"]["code"]
    usable: dict[str, tuple[list[dict], str]] = {}
    for c in EDA_COLUMNS:
        rows, label = _column_rows(ds, universe, c, sector_only)
        if rows:
            usable[c] = (rows, label)
    if not usable:
        return blocked("eda", ds, ["حداقل ۸ شرکت با مقدار معتبر برای هر شاخص"], "هیچ شاخصی در پایگاه BIAP نمونه‌ی کافی (۸ شرکت) برای تحلیل آماری ندارد.")
    miss = [{"column": EDA_LABELS[c], "present": sum(1 for r in primary if r.get(c) is not None),
             "missingPct": round(100 * (1 - sum(1 for r in primary if r.get(c) is not None) / total), 1) if total else 100.0} for c in EDA_COLUMNS]
    summary_rows, own_rows = [], []
    for c, (rows, label) in usable.items():
        vals = [r[c] for r in rows]
        d = st.describe(vals)
        summary_rows.append({"column": EDA_LABELS[c], "scope": label, **{k: (None if d.get(k) is None else round(d[k], 4)) for k in ("n", "mean", "median", "std", "min", "q1", "q3", "max", "skew")}})
        mine = next((r.get(c) for r in universe if r["code"] == code), None)
        if mine is not None:
            sv = sorted(vals)
            own_rows.append({"column": EDA_LABELS[c], "value": round(mine, 4), "percentile": round(100 * st.percentile_rank(sv, mine), 1), "outlier": st.iqr_outlier(sv, mine), "scope": label})
    focus = column if column in usable else next(iter(usable))
    rows, label = usable[focus]
    v = sorted(r[focus] for r in rows)
    h = st.histogram(v, 12, lo=st.quantile(v, 0.01), hi=st.quantile(v, 0.99))
    mine = next((r.get(focus) for r in universe if r["code"] == code), None)
    blocks: list[dict] = [
        {"type": "metrics", "items": [{"label": "نمونه‌ی شاخص انتخابی", "value": len(rows)}, {"label": "دامنه", "value": label}, {"label": "شرکت‌های اصلی ثبت‌شده", "value": total}]},
        {"type": "histogram", "title": f"توزیع {EDA_LABELS[focus]} ({label})", "bins": h["bins"], "clipped": h["clipped"], "n": h["n"], "marker": mine,
         "note": "مقادیر خارج از صدک ۱ تا ۹۹ در نمودار کوتاه شده‌اند و در clipped شمرده می‌شوند."},
        {"type": "table", "title": "خلاصه آماری", "columns": ["column", "scope", "n", "mean", "median", "std", "min", "q1", "q3", "max", "skew"], "rows": summary_rows},
    ]
    if own_rows:
        blocks.append({"type": "table", "title": "جایگاه این شرکت", "columns": ["column", "value", "percentile", "outlier", "scope"], "rows": own_rows})
    cols = [c for c in usable if c not in MARKET_COLUMNS or True]
    corr = []
    for i, a in enumerate(cols):
        for b2 in cols[i + 1:]:
            both = [r for r in universe if r.get("is_primary", 1) and r.get(a) is not None and r.get(b2) is not None]
            r_ = st.pearson([r[a] for r in both], [r[b2] for r in both]) if len(both) >= MIN_PEERS else None
            if r_ is not None:
                corr.append({"a": EDA_LABELS[a], "b": EDA_LABELS[b2], "r": round(r_, 3), "n": len(both)})
    corr.sort(key=lambda x: -abs(x["r"]))
    blocks.append({"type": "table", "title": "قوی‌ترین همبستگی‌ها (پیرسون، فقط جفت‌های هم‌نمونه)", "columns": ["a", "b", "r", "n"], "rows": corr[:8]})
    blocks.append({"type": "table", "title": "تحلیل مقادیر گمشده در کل شرکت‌های اصلی", "columns": ["column", "present", "missingPct"], "rows": miss})
    if len(ds["history"]) >= 3:
        blocks.append({"type": "line", "title": "تاریخچه قیمت ثبت‌شده در BIAP", "points": [{"x": h_["date"], "y": h_["price"]} for h_ in ds["history"]]})
    skipped = [EDA_LABELS[c] for c in EDA_COLUMNS if c not in usable]
    return envelope("eda", ds, "ok", f"تحلیل اکتشافی روی {len(usable)} شاخص با نمونه‌ی کافی از {total} شرکت اصلی (شاخص‌های مالی فقط برای شرکت‌های دارای صورت مالی).", blocks,
                    missing=[f"نمونه‌ی کافی: {s}" for s in skipped],
                    note="ورودی همان جدول تحلیلی BIAP است؛ نیازی به CSV نیست. شاخص‌های مالی تا گسترش پوشش CODAL نمونه‌ی کوچکی دارند و اندازه‌ی نمونه در جدول آمده است.")


# ---- anomaly / forecast ----------------------------------------------------------------------

def _series(ds: dict) -> tuple[list[str], list[float]]:
    pts = [(h["date"], h["price"]) for h in ds["history"] if h.get("price") and h["price"] > 0]
    pts.sort()
    seen, dates, prices = set(), [], []
    for d, p in pts:
        if d in seen:
            continue
        seen.add(d)
        dates.append(d)
        prices.append(p)
    return dates, prices


def anomaly(ds: dict) -> dict:
    dates, prices = _series(ds)
    if len(prices) < MIN_HISTORY_ANOMALY:
        return blocked("anomaly", ds, [f"حداقل {MIN_HISTORY_ANOMALY} مشاهده‌ی قیمت (اکنون {len(prices)})"],
                       "تاریخچه‌ی قیمت ثبت‌شده برای تشخیص ناهنجاری کافی نیست؛ جمع‌آوری روزانه ادامه دارد.")
    rets = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    z = st.mad_zscores(rets)
    flagged = [{"date": dates[i + 1], "return": round(rets[i], 4), "robustZ": round(z[i], 2)} for i in range(len(rets)) if z[i] is not None and abs(z[i]) >= 3.5]
    desc = st.describe(rets)
    blocks = [
        {"type": "metrics", "items": [{"label": "مشاهده", "value": len(prices)}, {"label": "ناهنجاری", "value": len(flagged)}, {"label": "انحراف معیار بازده", "value": round(desc["std"], 4)}]},
        {"type": "line", "title": "قیمت", "points": [{"x": d, "y": p} for d, p in zip(dates, prices)]},
        {"type": "table", "title": "بازده‌های ناهنجار (MAD-z ≥ 3.5)", "columns": ["date", "return", "robustZ"], "rows": flagged},
    ]
    note = "بازده‌ها بین مشاهده‌های متوالی ثبت‌شده محاسبه می‌شوند؛ اگر بین دو مشاهده روزهای معاملاتی جا افتاده باشد، بازده چندروزه است."
    return envelope("anomaly", ds, "ok", f"{len(flagged)} بازده ناهنجار در {len(rets)} بازده مشاهده‌شده.", blocks, note=note)


def forecast(ds: dict, horizon: int = 5) -> dict:
    dates, prices = _series(ds)
    n = len(prices)
    if n < MIN_HISTORY_FORECAST:
        return blocked("forecast", ds, [f"حداقل {MIN_HISTORY_FORECAST} مشاهده‌ی قیمت (اکنون {n})"],
                       "تاریخچه برای پیش‌بینی آماری کافی نیست و عددی ساخته نمی‌شود.")
    logp = [math.log(p) for p in prices]
    hold = max(5, n // 5)
    train, test = logp[:-hold], logp[-hold:]
    a, b, _ = st.linear_fit(train)
    lin_err = [abs(math.exp(a + b * (len(train) + i)) - math.exp(test[i])) / math.exp(test[i]) for i in range(hold)]
    naive_err = [abs(math.exp(train[-1]) - math.exp(test[i])) / math.exp(test[i]) for i in range(hold)]
    lin_mape, naive_mape = sum(lin_err) / hold, sum(naive_err) / hold
    use_trend = lin_mape < naive_mape
    a, b, rstd = st.linear_fit(logp)
    pts = []
    for h in range(1, horizon + 1):
        center = (a + b * (n - 1 + h)) if use_trend else logp[-1]
        width = 1.96 * rstd * math.sqrt(1 + h / n) if use_trend else 1.96 * (st.describe([logp[i] - logp[i - 1] for i in range(1, n)])["std"]) * math.sqrt(h)
        pts.append({"step": h, "forecast": round(math.exp(center), 2), "low": round(math.exp(center - width), 2), "high": round(math.exp(center + width), 2)})
    blocks = [
        {"type": "metrics", "items": [{"label": "روش", "value": "روند لگاریتمی" if use_trend else "ساده (آخرین قیمت)"},
                                      {"label": "خطای بازآزمایی (MAPE)", "value": round(min(lin_mape, naive_mape) * 100, 2)},
                                      {"label": "خطای روش ساده", "value": round(naive_mape * 100, 2)}]},
        {"type": "line", "title": "قیمت و پیش‌بینی", "points": [{"x": d, "y": p} for d, p in zip(dates, prices)],
         "forecast": [{"x": f"+{p['step']}", "y": p["forecast"], "low": p["low"], "high": p["high"]} for p in pts]},
        {"type": "table", "title": "بازه پیش‌بینی ۹۵٪", "columns": ["step", "forecast", "low", "high"], "rows": pts},
    ]
    return envelope("forecast", ds, "ok", "پیش‌بینی آماری بر پایه‌ی مشاهده‌های ثبت‌شده؛ روش با بازآزمایی روی انتهای سری انتخاب شد.", blocks,
                    note="این یک برآورد آماری است، توصیه‌ی معاملاتی نیست؛ اگر روند از روش ساده بهتر نباشد، روش ساده استفاده می‌شود.")


# ---- financial model / scenario --------------------------------------------------------------

def _model(ds: dict, growth: Optional[float], margin: Optional[float], years: int = 3) -> Optional[list[dict]]:
    cur = ds["fundamentals"].get("current") or {}
    rev, npf = cur.get("revenue"), cur.get("net_profit")
    if rev is None or npf is None or rev == 0:
        return None
    g0 = ds["ratios"].get("revenue_growth", {}).get("value") if growth is None else growth
    g0 = 0.0 if g0 is None else max(-0.3, min(0.6, g0))
    m = (npf / rev) if margin is None else margin
    out, r = [], rev
    for y in range(1, years + 1):
        g = g0 * (0.5 ** (y - 1))
        r = r * (1 + g)
        out.append({"year": y, "growth": round(g, 4), "revenue": round(r, 2), "netProfit": round(r * m, 2), "netMargin": round(m, 4)})
    return out


def financial_model(ds: dict, growth: Optional[float] = None, margin: Optional[float] = None) -> dict:
    cur = ds["fundamentals"].get("current") or {}
    if cur.get("revenue") is None or cur.get("net_profit") is None:
        return blocked("financial-model", ds, [m for m in ("درآمد دوره", "سود خالص") if cur.get({"درآمد دوره": "revenue", "سود خالص": "net_profit"}[m]) is None],
                       "مدل مالی به درآمد و سود خالص تأییدشده نیاز دارد.")
    proj = _model(ds, growth, margin)
    if proj is None:
        return blocked("financial-model", ds, ["درآمد غیرصفر"], "درآمد صفر است و مدل ساخته نمی‌شود.")
    g_obs = ds["ratios"].get("revenue_growth", {}).get("value")
    market = ds["market"]
    val_rows = []
    eps, sector_pe, pe = num(market.get("eps_value")), num(market.get("sector_avg_pe")), num(market.get("pe"))
    if eps is not None and sector_pe and eps > 0:
        val_rows.append({"method": "EPS × میانگین P/E صنعت", "value": round(eps * sector_pe, 2), "inputs": f"EPS={eps}, P/E صنعت={sector_pe}"})
    blocks = [
        {"type": "table", "title": "فرضیات (قابل تغییر)", "columns": ["assumption", "value", "origin"], "rows": [
            {"assumption": "رشد درآمد سال اول", "value": growth if growth is not None else (round(g_obs, 4) if g_obs is not None else 0), "origin": "ورودی کاربر" if growth is not None else ("مشاهده‌شده از صورت مالی" if g_obs is not None else "رشد مشاهده‌شده موجود نیست؛ صفر")},
            {"assumption": "افت نرخ رشد در هر سال", "value": 0.5, "origin": "فرض مدل"},
            {"assumption": "حاشیه سود خالص", "value": margin if margin is not None else round(cur["net_profit"] / cur["revenue"], 4), "origin": "ورودی کاربر" if margin is not None else "مشاهده‌شده"}]},
        {"type": "table", "title": "پیش‌بینی ۳ ساله", "columns": ["year", "growth", "revenue", "netProfit", "netMargin"], "rows": proj},
        {"type": "bars", "title": "سود خالص پیش‌بینی‌شده", "items": [{"label": f"سال {p['year']}", "value": p["netProfit"]} for p in proj]},
    ]
    if val_rows:
        blocks.append({"type": "table", "title": "ارزش‌گذاری نسبی", "columns": ["method", "value", "inputs"], "rows": val_rows})
    else:
        blocks.append({"type": "notice", "tone": "info", "text": "ارزش‌گذاری نسبی نیاز به EPS مثبت و میانگین P/E صنعت دارد که برای این شرکت موجود نیست.", "missing": ["EPS مثبت", "P/E صنعت"]})
    return envelope("financial-model", ds, "ok", "مدل مالی ساده از آخرین صورت مالی؛ فرضیات صریح و قابل تغییر هستند.", blocks,
                    note="واحد ارقام همان واحد صورت مالی CODAL است. مدل پیش‌بینی قطعی نیست.")


def scenario(ds: dict, spread: float = 0.10) -> dict:
    cur = ds["fundamentals"].get("current") or {}
    if cur.get("revenue") is None or cur.get("net_profit") is None:
        return blocked("scenario", ds, ["درآمد دوره", "سود خالص"], "سناریو به درآمد و سود خالص تأییدشده نیاز دارد.")
    g = ds["ratios"].get("revenue_growth", {}).get("value") or 0.0
    base_m = cur["net_profit"] / cur["revenue"] if cur["revenue"] else 0.0
    cases = {"بدبینانه": (g - spread, base_m - spread / 2), "پایه": (g, base_m), "خوش‌بینانه": (g + spread, base_m + spread / 2)}
    rows = []
    for name, (gr, mr) in cases.items():
        p = _model(ds, gr, mr, 1)
        rows.append({"scenario": name, "growth": round(gr, 4), "margin": round(mr, 4), "revenue": p[0]["revenue"], "netProfit": p[0]["netProfit"]})
    return envelope("scenario", ds, "ok", "سه سناریوی یک‌ساله حول مقدار مشاهده‌شده؛ عرض سناریو فرض کاربر/مدل است نه داده.", [
        {"type": "table", "title": "سناریوها", "columns": ["scenario", "growth", "margin", "revenue", "netProfit"], "rows": rows},
        {"type": "bars", "title": "سود خالص سال بعد", "items": [{"label": r["scenario"], "value": r["netProfit"]} for r in rows]},
        {"type": "metrics", "items": [{"label": "عرض سناریو (فرض)", "value": spread}]}],
        note="عرض سناریو (±۱۰ واحد درصد رشد، ±۵ حاشیه) فرض است و از داده استخراج نشده؛ در درخواست قابل تغییر است.")


# ---- peers: SWOT / market entry --------------------------------------------------------------

def _peers(ds: dict, universe: list[dict]) -> tuple[list[dict], str]:
    sector = ds["identity"].get("sector")
    rows = [r for r in comparable(universe, ds["identity"]["code"]) if r["code"] != ds["identity"]["code"]]
    same = [r for r in rows if sector and r.get("sector") == sector]
    return (same, f"گروه {sector}") if len(same) >= MIN_PEERS else (rows, "شرکت‌های هم‌دسته")


def swot(ds: dict, universe: list[dict]) -> dict:
    if not ds["fundamentals"].get("present"):
        return blocked("swot", ds, ["صورت مالی CODAL"], "SWOT بدون صورت مالی تأییدشده ساخته نمی‌شود.")
    peers, scope = _peers(ds, universe)
    if len(peers) < MIN_PEERS:
        return blocked("swot", ds, ["حداقل ۸ شرکت برای مقایسه"], "تعداد شرکت‌های قابل مقایسه کافی نیست.")
    higher_better = {"net_margin": "حاشیه سود خالص", "operating_margin": "حاشیه سود عملیاتی", "roe": "ROE", "roa": "ROA", "current_ratio": "نسبت جاری",
                     "revenue_growth": "رشد درآمد", "profit_growth": "رشد سود", "cfo_to_profit": "کیفیت سود"}
    lower_better = {"debt_ratio": "نسبت بدهی"}
    S, W, O, T = [], [], [], []
    for key, label in {**higher_better, **lower_better}.items():
        mine = ds["ratios"].get(key, {}).get("value")
        vals = sorted(r[key] for r in peers if r.get(key) is not None)
        if mine is None or len(vals) < MIN_PEERS:
            continue
        pr = st.percentile_rank(vals, mine)
        good = pr if key in higher_better else 1 - pr
        evidence = f"{label}: {mine:.3f} • صدک {round(100 * pr)} در {scope} (n={len(vals)})"
        if good >= 0.75:
            S.append(evidence)
        elif good <= 0.25:
            W.append(evidence)
    g, pg = ds["ratios"].get("revenue_growth", {}).get("value"), ds["ratios"].get("profit_growth", {}).get("value")
    if g is not None and g > 0 and pg is not None and pg > 0:
        O.append(f"رشد همزمان درآمد ({g:.1%}) و سود ({pg:.1%}) نسبت به دوره قبل")
    cfo = ds["ratios"].get("cfo_to_profit", {}).get("value")
    if cfo is not None and cfo < 0.5:
        T.append(f"جریان نقد عملیاتی کمتر از نیمی از سود است (نسبت {cfo:.2f})")
    opinion = ds["fundamentals"].get("auditOpinion")
    if opinion in ("qualified", "adverse", "disclaimer"):
        T.append(f"نظر حسابرس: {opinion}")
    debt = ds["ratios"].get("debt_ratio", {}).get("value")
    if debt is not None and debt > 0.8:
        T.append(f"اهرم بالا: نسبت بدهی {debt:.2f}")
    comp = sorted([r for r in peers if r.get("market_cap")], key=lambda r: -r["market_cap"])[:5]
    comp_rows = [{"symbol": r["symbol"], "net_margin": fmt_ratio(r.get("net_margin")), "roe": fmt_ratio(r.get("roe")), "debt_ratio": fmt_ratio(r.get("debt_ratio")), "pe": fmt_ratio(r.get("pe"))} for r in comp]
    blocks = [{"type": "swot", "strengths": S, "weaknesses": W, "opportunities": O, "threats": T},
              {"type": "table", "title": f"بزرگ‌ترین رقبا بر اساس ارزش بازار ({scope})", "columns": ["symbol", "net_margin", "roe", "debt_ratio", "pe"], "rows": comp_rows}]
    return envelope("swot", ds, "ok" if (S or W or O or T) else "partial", "هر مورد SWOT از مقایسه‌ی عددی با شرکت‌های هم‌گروه می‌آید؛ متن توصیفی بدون شاهد تولید نمی‌شود.", blocks,
                    note="فرصت‌ها و تهدیدهای برون‌سازمانی (مقررات، رقابت‌های خاص) از داده‌ی عمومی استخراج‌شدنی نیستند.")


def market_entry(ds: dict, universe: list[dict]) -> dict:
    sector = ds["identity"].get("sector")
    if not sector:
        return blocked("market-entry", ds, ["گروه صنعت"], "گروه صنعت شرکت ثبت نشده است.")
    base = comparable(universe, ds["identity"]["code"])
    same = [r for r in base if r.get("sector") == sector]
    if len(same) < MIN_PEERS:
        return blocked("market-entry", ds, ["حداقل ۸ شرکت هم‌گروه"], f"فقط {len(same)} شرکت هم‌گروه صورت مالی دارند.")
    allr = base
    rows = []
    for key in ("net_margin", "revenue_growth", "roe", "debt_ratio", "pe"):
        a = st.describe([r.get(key) for r in same]); b = st.describe([r.get(key) for r in allr])
        if a["n"] >= MIN_PEERS and b["n"]:
            rows.append({"metric": EDA_LABELS.get(key, key), "sectorMedian": round(a["median"], 4), "marketMedian": round(b["median"], 4), "n": a["n"]})
    return envelope("market-entry", ds, "ok", f"مقایسه‌ی صنعت {sector} با کل بازار روی {len(same)} شرکت.", [
        {"type": "table", "title": "میانه صنعت در برابر بازار", "columns": ["metric", "sectorMedian", "marketMedian", "n"], "rows": rows}],
        note="این ماژول شاهد عددی صنعت را نشان می‌دهد؛ ارزیابی ورود به بازار به داده‌ی تقاضا و هزینه‌ی داخلی نیاز دارد.")


# ---- composites ------------------------------------------------------------------------------

def composite(module: str, ds: dict, universe: list[dict]) -> dict:
    if ds["tier"] == TIER_REGISTERED:
        return blocked(module, ds, ["قیمت بازار", "صورت مالی CODAL"], "برای این شرکت هنوز هیچ داده‌ی تأییدشده‌ای ذخیره نشده است.")
    k = kpi(ds)
    items = [i for b in k["blocks"] if b["type"] == "kpi_table" for i in b["items"]]
    top = [i for i in items if i["status"] == "ok"][:6]
    blocks: list[dict] = [{"type": "metrics", "items": [{"label": i["label"], "value": i["value"], "unit": i["unit"]} for i in top]},
                          {"type": "table", "title": "وضعیت داده", "columns": ["item", "value"], "rows": [
                              {"item": "سطح داده", "value": ds["tier"]}, {"item": "منبع صورت مالی", "value": ds["provenance"].get("statementTitle") or "—"},
                              {"item": "شماره رهگیری", "value": ds["provenance"].get("tracingNo") or "—"},
                              {"item": "آخرین به‌روزرسانی پایه", "value": ds["provenance"].get("baselineEnrichedAt") or "—"}]}]
    miss = k["missing"]
    if module in ("executive-report", "mbr", "report"):
        sw = swot(ds, universe)
        if sw["status"] != "blocked":
            blocks.append(sw["blocks"][0])
        blocks.append({"type": "bullets", "title": "اقدام بعدی", "items": [f"تکمیل ورودی: {m}" for m in miss] or ["داده‌ی ضروری کامل است؛ به‌روزرسانی دوره‌ای ادامه دارد."]})
    return envelope(module, ds, "ok" if ds["tier"] == TIER_FULL else "partial", "گزارش از همان شاخص‌های محاسبه‌شده‌ی KPI و صورت مالی ساخته شد.", blocks, missing=miss)


def compute(module: str, ds: dict, universe: list[dict], params: Optional[dict] = None) -> dict:
    params = params or {}
    if module == "kpi-extract":
        return kpi(ds)
    if module == "eda":
        return eda(ds, universe, column=params.get("column"), sector_only=bool(params.get("sectorOnly")))
    if module == "anomaly":
        return anomaly(ds)
    if module == "forecast":
        return forecast(ds, int(params.get("horizon") or 5))
    if module == "financial-model":
        return financial_model(ds, num(params.get("growth")), num(params.get("margin")))
    if module == "scenario":
        return scenario(ds, num(params.get("spread")) or 0.10)
    if module == "swot":
        return swot(ds, universe)
    if module == "market-entry":
        return market_entry(ds, universe)
    if module in ("dashboard", "report", "executive-report", "mbr"):
        return composite(module, ds, universe)
    raise KeyError(module)
