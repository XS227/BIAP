"""Module computations for listed companies. Every function takes the shared dataset (module_dataset)
and the universe table; none of them knows a specific symbol. A module that cannot be computed returns
status "blocked" with the exact missing inputs, never a placeholder number."""
from __future__ import annotations

import math
from typing import Any, Optional

import module_stats as st
from module_dataset import compute_ratios, TIER_FULL, TIER_MARKET, TIER_PARTIAL, TIER_REGISTERED, UNIVERSE_RATIO_KEYS, num

MIN_HISTORY_ANOMALY = 15
MIN_HISTORY_FORECAST = 30
MIN_PEERS = 8

LISTED_MODULES = ("eda", "sql", "kpi-extract", "anomaly", "forecast", "dashboard", "report", "swot", "market-entry",
                  "financial-model", "scenario", "executive-report", "mbr")
PRIVATE_MODULES = ("business-kpi", "governance", "crm", "campaign", "pricing", "plan", "unit", "journey", "voc", "behavior")

# Required inputs per listed-company module (data contract). "any" = at least one of the group.
CONTRACTS: dict[str, dict] = {
    "eda": {"title": "EDA Explorer", "needs_any": ["market.price", "fundamentals", "history>=3"]},
    "sql": {"title": "SQL / Data Query", "needs": [("universe", "جدول‌های تحلیلی BIAP")]},
    "kpi-extract": {"title": "KPI", "needs_any": ["market.price", "fundamentals"]},
    "anomaly": {"title": "تشخیص ناهنجاری", "needs": [("history>=15", "حداقل ۱۵ مشاهده‌ی قیمت روزانه")]},
    "forecast": {"title": "پیش‌بینی آماری", "needs": [("history>=30", "حداقل ۳۰ مشاهده‌ی قیمت روزانه")]},
    "dashboard": {"title": "BI Dashboard", "needs_any": ["market.price", "fundamentals"]},
    "report": {"title": "گزارش تحلیلی", "needs_any": ["market.price", "fundamentals"]},
    "swot": {"title": "SWOT + رقبا", "needs": [("fundamentals", "صورت مالی CODAL"), ("peers>=8", "حداقل ۸ شرکت هم‌گروه یا بازار برای مقایسه")]},
    "market-entry": {"title": "فرصت و ورود به بازار", "needs": [("sector", "گروه صنعت")]},
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
            if not (has_fund or has_price or (key == "eda" and n_hist >= 3)):
                missing.append("قیمت بازار، صورت مالی CODAL یا حداقل ۳ مشاهده‌ی قیمت")
        if missing:
            status = "blocked"
        elif key in ("eda", "kpi-extract", "dashboard", "report", "executive-report", "mbr") and not (has_fund and has_price):
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
                      "status": "ok" if value is not None else "missing", "missing": extra_missing or [], "kind": "public", "requiresPrivateData": False})

    price = market.get("price")
    pe = num(market.get("pe"))
    add("بازار", "price", "قیمت جاری", price, "ریال", "آخرین قیمت معامله/پایانی از منبع بازار", ["last_price"], f"بازار ({ds['provenance'].get('priceSource') or 'TSETMC/Tindex'})",
        None if price is not None else ["قیمت جاری از منبع بازار دریافت نشده است"])
    hist = ds.get("history") or []
    if hist:
        last = hist[-1]
        add("بازار", "last_recorded_close", f"آخرین قیمت ثبت‌شده در تاریخچه ({last['date']})", last["price"], "ریال",
            "آخرین مشاهده‌ی روزانه‌ی ذخیره‌شده در BIAP؛ قیمت جاری نیست", ["history"], f"تاریخچه BIAP • {len(hist)} مشاهده")
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
    labels = compute_ratios({"current": {}, "prev": {}, "periodType": "unknown"})
    for key, group in groups.items():
        r = ratios.get(key)
        if r is None:
            lab = labels.get(key) or {}
            add(group, key, lab.get("label", key), None, "نسبت", lab.get("formula", "—"), lab.get("inputs", []), "CODAL", ["صورت مالی CODAL"])
            continue
        unit = "روز" if key == "receivable_days" else ("×" if key in ("current_ratio", "debt_to_equity", "asset_turnover") else "نسبت")
        add(group, key, r["label"], r["value"], unit, r["formula"], r["inputs"], f"CODAL • {view.get('scope') or 'نامشخص'}", r.get("missing") or ([r["reason"]] if r.get("reason") else []))
        if r.get("unverified"):
            items[-1]["status"] = "unverified"
    ok = [i for i in items if i["status"] == "ok"]
    missing_inputs = sorted({m for i in items for m in i["missing"]})
    if not ok:
        return blocked("kpi-extract", ds, missing_inputs or ["قیمت بازار", "صورت مالی CODAL"], "هیچ شاخصی با داده‌ی تأییدشده قابل محاسبه نیست.")
    status = "ok" if len(ok) == len(items) else "partial"
    return envelope("kpi-extract", ds, status, f"{len(ok)} از {len(items)} شاخص محاسبه شد؛ هر شاخص فرمول، ورودی و منبع دارد.",
                    [{"type": "kpi_table", "items": items},
                     {"type": "notice", "tone": "info", "text": "شاخص‌های بالا عمومی‌اند و از CODAL/TSETMC خودکار محاسبه می‌شوند؛ Excel نمی‌خواهند. فقط شاخص‌های خصوصی (هزینه‌ی جذب مشتری، CRM، هزینه‌های داخلی) به داده‌ی خود شما نیاز دارند.",
                      "privateKpis": ["هزینه‌ی جذب مشتری (CAC)", "نرخ تبدیل CRM", "هزینه‌های داخلی", "حاشیه‌ی محصول/کانال"]}], missing=missing_inputs,
                    note="مقادیر CODAL فقط از یک صورت مالی با دامنه‌ی مشخص و بدون اختلاط تلفیقی/جداگانه می‌آیند.")


# ---- EDA -------------------------------------------------------------------------------------

EDA_COLUMNS = ["net_margin", "operating_margin", "roa", "roe", "debt_ratio", "current_ratio", "revenue_growth", "profit_growth", "cfo_to_profit",
               "pe", "change_percent", "market_cap", "trade_value"]
EDA_LABELS = {"net_margin": "حاشیه سود خالص", "operating_margin": "حاشیه سود عملیاتی", "roa": "ROA", "roe": "ROE", "debt_ratio": "نسبت بدهی",
              "current_ratio": "نسبت جاری", "revenue_growth": "رشد درآمد", "profit_growth": "رشد سود", "cfo_to_profit": "جریان نقد ÷ سود", "pe": "P/E",
              "change_percent": "تغییر روزانه (٪)", "market_cap": "ارزش بازار", "trade_value": "ارزش معاملات"}
MARKET_COLUMNS = {"pe", "change_percent", "market_cap", "trade_value"}
# how the client must render each column's numbers: fraction -> ٪, times -> ×, percent (already ×100) -> ٪, rial -> compact money
EDA_UNITS = {"net_margin": "fraction", "operating_margin": "fraction", "roa": "fraction", "roe": "fraction", "debt_ratio": "fraction",
             "current_ratio": "times", "revenue_growth": "fraction", "profit_growth": "fraction", "cfo_to_profit": "times", "pe": "times",
             "change_percent": "percent", "market_cap": "rial", "trade_value": "rial"}
POSITIVE_ONLY = {"pe", "market_cap", "trade_value"}


def _column_rows(ds: dict, universe: list[dict], col: str, sector_only: bool) -> tuple[list[dict], str]:
    """Rows to describe ``col`` and the scope label. Financial ratios prefer the company's own category;
    when that is too small they widen to every primary company with statements (and say so)."""
    primary = [r for r in universe if r.get("is_primary", 1) and r.get(col) is not None]
    if col not in MARKET_COLUMNS:  # statements of long-past periods and unverified balance sheets never enter peer statistics
        primary = [r for r in primary if not r.get("stale") and r.get("verification") != "unverified"]
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


MIN_CORR_PAIRS = 15


def _own_value(ds: dict, col: str) -> tuple[Optional[float], str, Optional[str]]:
    """This company's own value for an EDA column, the source label and, when absent, the precise reason."""
    if col in MARKET_COLUMNS:
        key = {"pe": "pe", "change_percent": "change_percent", "market_cap": "market_cap", "trade_value": "trade_value_today"}[col]
        v = num(ds["market"].get(key))
        if v is None:
            return None, "بازار", "قیمت/داده‌ی جاری بازار برای این شرکت ثبت نشده است" if ds["market"].get("price") is None else "این فیلد از منبع بازار دریافت نشده است"
        return v, "بازار", None
    r = ds["ratios"].get(col)
    view = ds["fundamentals"]
    if not view.get("present"):
        return None, "CODAL", "صورت مالی CODAL برای این شرکت ثبت نشده است"
    src = f"CODAL • {'تلفیقی' if view.get('scope') == 'consolidated' else 'جداگانه' if view.get('scope') == 'standalone' else 'دامنه نامشخص'}"
    if view.get("periodEnd"):
        src += f" • دوره‌ی منتهی به {view['periodEnd']}"
    if (view.get("verification") or {}).get("stale"):
        src += " (قدیمی؛ در آمار مقایسه‌ای نیست)"
    if view.get("tracingNo"):
        src += f" • رهگیری {view['tracingNo']}"
    if r is None or r["value"] is None:
        miss = (r or {}).get("missing") or []
        return None, src, ("ورودی‌های ناموجود: " + "، ".join(miss)) if miss else ((r or {}).get("reason") or "قابل محاسبه نیست")
    return r["value"], src, None


def eda(ds: dict, universe: list[dict], *, column: Optional[str] = None, sector_only: bool = False) -> dict:
    primary = [r for r in universe if r.get("is_primary", 1)]
    total = len(primary)
    code = ds["identity"]["code"]
    usable: dict[str, tuple[list[dict], str]] = {}
    for c in EDA_COLUMNS:
        rows, label = _column_rows(ds, universe, c, sector_only)
        if rows:
            usable[c] = (rows, label)
    # 1) company-specific profile: always this company's own numbers, with source and an exact reason when absent
    profile, own_rows = [], []
    for c in EDA_COLUMNS:
        mine, source, why = _own_value(ds, c)
        entry: dict[str, Any] = {"column": EDA_LABELS[c], "unit": EDA_UNITS[c], "value": None if mine is None else round(mine, 4), "source": source,
                                 "status": "ok" if mine is not None else "missing", "reason": why,
                                 "sampleN": None, "peerMedian": None, "percentile": None, "outlier": None, "scope": None}
        if c in usable:
            rows, label = usable[c]
            vals = sorted(r[c] for r in rows)
            entry.update({"sampleN": len(vals), "scope": label, "peerMedian": round(st.quantile(vals, 0.5), 4)})
            if mine is not None and not (c in POSITIVE_ONLY and mine <= 0):
                entry["percentile"] = round(100 * st.percentile_rank(vals, mine), 1)
                entry["outlier"] = st.iqr_outlier(vals, mine)
                own_rows.append({"column": EDA_LABELS[c], "unit": EDA_UNITS[c], "value": entry["value"], "percentile": entry["percentile"], "outlier": entry["outlier"], "scope": label})
        elif mine is not None:
            entry["reason"] = f"نمونه‌ی مقایسه کافی نیست (کمتر از {MIN_PEERS} شرکت)؛ جایگاه صدکی نمایش داده نمی‌شود"
        profile.append(entry)
    have = [e for e in profile if e["status"] == "ok"]
    if not have and len(ds["history"]) < 3:
        reasons = sorted({e["reason"] for e in profile if e["reason"]})
        return blocked("eda", ds, reasons or ["داده‌ی خود شرکت"], "برای این شرکت هیچ شاخص یا تاریخچه‌ی قیمتی ثبت نشده است؛ آمار کل بازار به‌جای آن نمایش داده نمی‌شود.")
    blocks: list[dict] = [
        {"type": "metrics", "title": "این شرکت", "scopeKind": "company",
         "items": [{"label": "شاخص‌های محاسبه‌شده برای این شرکت", "value": f"{len(have)} از {len(profile)}"},
                   {"label": "مشاهده‌های قیمت ثبت‌شده", "value": len(ds["history"])},
                   {"label": "شرکت‌های اصلی ثبت‌شده (کل بازار)", "value": total}]},
        {"type": "table", "title": "شاخص‌های همین شرکت (نه آمار کل بازار)", "scopeKind": "company",
         "columns": ["column", "value", "source", "peerMedian", "percentile", "sampleN", "scope", "reason"], "rows": profile},
    ]
    # 2) the company's own price record (explicit count; never confused with a current quote)
    if len(ds["history"]) >= 3:
        blocks.append({"type": "line", "title": f"تاریخچه قیمت ثبت‌شده همین شرکت ({len(ds['history'])} مشاهده، از {ds['history'][0]['date']} تا {ds['history'][-1]['date']})",
                       "scopeKind": "company", "points": [{"x": h_["date"], "y": h_["price"]} for h_ in ds["history"]]})
    else:
        blocks.append({"type": "notice", "tone": "info", "scopeKind": "company",
                       "text": f"تاریخچه‌ی قیمت این شرکت {len(ds['history'])} مشاهده دارد؛ برای نمودار حداقل ۳ مشاهده لازم است."})
    # 3) whole-market statistics, always labelled as such
    if usable:
        focus = column if column in usable else next((c for c in usable if any(e["column"] == EDA_LABELS[c] and e["status"] == "ok" for e in profile)), next(iter(usable)))
        rows, label = usable[focus]
        v = sorted(r[focus] for r in rows)
        lo, hi = st.quantile(v, 0.01), st.quantile(v, 0.99)
        h = st.histogram(v, 12, lo=lo, hi=hi)
        mine = next((e["value"] for e in profile if e["column"] == EDA_LABELS[focus]), None)
        in_range = mine is not None and lo is not None and lo <= mine <= hi
        blocks.append({"type": "histogram", "scopeKind": "market", "title": f"توزیع {EDA_LABELS[focus]} در {label} (آمار نمونه، نه این شرکت)",
                       "bins": h["bins"], "clipped": h["clipped"], "n": h["n"], "marker": mine, "markerInRange": in_range, "unit": EDA_UNITS[focus],
                       "range": [lo, hi], "note": "مقادیر خارج از صدک ۱ تا ۹۹ در نمودار کوتاه شده‌اند و در clipped شمرده می‌شوند."
                       + ("" if mine is None or in_range else " مقدار این شرکت خارج از بازه‌ی نمودار است.")})
        summary_rows = []
        for c, (rws, lab) in usable.items():
            d = st.describe([r[c] for r in rws])
            summary_rows.append({"column": EDA_LABELS[c], "unit": EDA_UNITS[c], "scope": lab, **{k: (None if d.get(k) is None else round(d[k], 4)) for k in ("n", "mean", "median", "std", "min", "q1", "q3", "max", "skew")}})
        blocks.append({"type": "table", "title": "خلاصه آماری نمونه‌ی مقایسه (کل بازار/هم‌دسته)", "scopeKind": "market",
                       "columns": ["column", "scope", "n", "mean", "median", "std", "min", "q1", "q3", "max", "skew"], "rows": summary_rows})
        if own_rows:
            blocks.append({"type": "table", "title": "جایگاه این شرکت در نمونه", "scopeKind": "company", "columns": ["column", "value", "percentile", "outlier", "scope"], "rows": own_rows})
        corr = []
        cols = list(usable)
        for i, a in enumerate(cols):
            for b2 in cols[i + 1:]:
                both = [r for r in primary if r.get(a) is not None and r.get(b2) is not None]
                r_ = st.spearman([r[a] for r in both], [r[b2] for r in both]) if len(both) >= MIN_CORR_PAIRS else None
                if r_ is not None:
                    corr.append({"a": EDA_LABELS[a], "b": EDA_LABELS[b2], "r": round(r_, 3), "n": len(both)})
        corr.sort(key=lambda x: -abs(x["r"]))
        blocks.append({"type": "table", "title": f"همبستگی رتبه‌ای اسپیرمن در کل بازار (حداقل {MIN_CORR_PAIRS} جفت؛ مقدار پرت جهت را تعیین نمی‌کند)", "scopeKind": "market",
                       "columns": ["a", "b", "r", "n"], "rows": corr[:8]})
    miss = [{"column": EDA_LABELS[c], "present": sum(1 for r in primary if r.get(c) is not None),
             "missingPct": round(100 * (1 - sum(1 for r in primary if r.get(c) is not None) / total), 1) if total else 100.0} for c in EDA_COLUMNS]
    blocks.append({"type": "table", "title": "تحلیل مقادیر گمشده در کل شرکت‌های اصلی (کل بازار)", "scopeKind": "market", "columns": ["column", "present", "missingPct"], "rows": miss})
    skipped = [EDA_LABELS[c] for c in EDA_COLUMNS if c not in usable]
    absent = [f"{e['column']}: {e['reason']}" for e in profile if e["status"] == "missing"]
    status = "ok" if len(have) == len(profile) else "partial"
    return envelope("eda", ds, status,
                    f"{len(have)} از {len(profile)} شاخص برای همین شرکت محاسبه شد؛ جدول‌های آمار نمونه با برچسب «کل بازار» جدا شده‌اند.", blocks,
                    missing=absent + [f"نمونه‌ی مقایسه‌ی کافی نیست: {s}" for s in skipped],
                    note="شاخص‌های مالی از آخرین صورت مالی همین شرکت می‌آیند؛ نمونه‌ی مقایسه فقط شرکت‌های دارای صورت مالی (سالانه، تلفیقی یا جداگانه) است و اندازه‌ی آن در جدول آمده است. نیازی به CSV نیست.")


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
    """Sector vs market medians, each metric on its own valid sample (financial ratios need CODAL peers, P/E and
    market size only need market data, so a sector with few statements still gets the market metrics)."""
    sector = ds["identity"].get("sector")
    if not sector:
        return blocked("market-entry", ds, ["گروه صنعت"], "گروه صنعت شرکت ثبت نشده است.")
    primary = [r for r in universe if r.get("is_primary", 1)]
    code = ds["identity"]["code"]
    own = next((r for r in universe if r["code"] == code), None)
    cat = own.get("category") if own else None
    rows, limits = [], []
    for key in ("net_margin", "revenue_growth", "roe", "debt_ratio", "pe", "market_cap"):
        market_metric = key in MARKET_COLUMNS
        pool = [r for r in primary if r.get(key) is not None and (key not in POSITIVE_ONLY or r[key] > 0)]
        same = [r for r in pool if r.get("sector") == sector]
        scope = f"گروه {sector}"
        if len(same) < MIN_PEERS and cat and not market_metric:
            same, scope = [r for r in pool if r.get("category") == cat], "هم‌دسته (گروه صنعت نمونه‌ی کافی ندارد)"
        if len(same) < MIN_PEERS or len(pool) < MIN_PEERS:
            limits.append(f"{EDA_LABELS.get(key, key)}: فقط {len(same)} شرکت با داده‌ی معتبر در {scope}")
            continue
        a, b2 = st.describe([r[key] for r in same]), st.describe([r[key] for r in pool])
        mine = next((e for e in [_own_value(ds, key)] if e[0] is not None), None)
        rows.append({"metric": EDA_LABELS.get(key, key), "unit": EDA_UNITS.get(key), "scope": scope, "sectorMedian": round(a["median"], 4), "marketMedian": round(b2["median"], 4),
                     "n": a["n"], "company": None if mine is None else round(mine[0], 4)})
    if not rows:
        return blocked("market-entry", ds, limits or ["حداقل ۸ شرکت هم‌گروه با داده‌ی معتبر"], f"برای گروه {sector} نمونه‌ی کافی (۸ شرکت) در هیچ شاخص وجود ندارد.")
    return envelope("market-entry", ds, "ok" if not limits else "partial", f"مقایسه‌ی صنعت {sector} با کل بازار روی {len(rows)} شاخص با نمونه‌ی کافی.", [
        {"type": "table", "title": "میانه صنعت در برابر بازار (هر شاخص با نمونه‌ی خودش)", "columns": ["metric", "scope", "sectorMedian", "marketMedian", "company", "n"], "rows": rows}],
        missing=limits, note="این ماژول شاهد عددی صنعت را نشان می‌دهد؛ ارزیابی ورود به بازار به داده‌ی تقاضا و هزینه‌ی داخلی نیاز دارد.")


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
