"""Analytics over the user's OWN operational data (uploaded dataset, KPI register, CRM).

Public listed-company figures are never substituted here: if the user's data lacks a required column
the module returns ``needs_private_data`` with the exact column names it is waiting for.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import module_stats as st

ALIASES = {
    "period": ["date", "month", "period", "تاریخ", "ماه", "دوره"],
    "revenue": ["revenue", "sales", "فروش", "درآمد"],
    "cost": ["cost", "expense", "expenses", "هزینه"],
    "customers": ["customers", "customer_count", "مشتری", "تعداد مشتری"],
    "new_customers": ["new_customers", "new_users", "مشتری جدید"],
    "churned": ["churned", "churn", "lost_customers", "ریزش"],
    "spend": ["marketing_spend", "ad_spend", "spend", "هزینه بازاریابی", "هزینه تبلیغات"],
    "conversions": ["conversions", "orders", "leads", "تبدیل", "سفارش"],
    "channel": ["channel", "campaign", "کانال", "کمپین"],
    "price": ["price", "unit_price", "قیمت"],
    "quantity": ["quantity", "units", "units_sold", "qty", "تعداد", "تعداد فروش"],
    "stage": ["stage", "step", "funnel_stage", "مرحله"],
    "users": ["users", "count", "visitors", "کاربر", "تعداد کاربر"],
    "theme": ["theme", "topic", "category", "موضوع", "دسته"],
    "score": ["score", "rating", "sentiment", "nps", "امتیاز"],
}


class Dataset:
    def __init__(self, ds: dict) -> None:
        self.name = ds.get("name") or "dataset"
        self.columns = [str(c) for c in ds.get("columns") or []]
        self.rows = [r for r in ds.get("rows") or [] if isinstance(r, dict)]
        self._lower = {c.strip().lower(): c for c in self.columns}

    def col(self, key: str) -> Optional[str]:
        for alias in ALIASES[key]:
            hit = self._lower.get(alias.lower())
            if hit:
                return hit
        return None

    def values(self, column: Optional[str]) -> list[Any]:
        return [r.get(column) for r in self.rows] if column else []

    def numbers(self, column: Optional[str]) -> list[Optional[float]]:
        out = []
        for v in self.values(column):
            try:
                f = float(str(v).replace(",", "")) if v not in (None, "") else None
            except ValueError:
                f = None
            out.append(f if f is not None and math.isfinite(f) else None)
        return out


def _env(module: str, title: str, status: str, summary: str, blocks: list[dict], missing: Optional[list[str]] = None, note: Optional[str] = None) -> dict:
    return {"module": module, "title": title, "status": status, "summary": summary, "blocks": blocks, "missing": missing or [], "note": note,
            "tier": "private", "provenance": {"source": "private dataset"}, "quality": {"missing": missing or [], "warnings": []}, "company": None}


def _need(module: str, title: str, d: Optional[Dataset], required: list[tuple[str, str]], any_of: Optional[list[str]] = None) -> Optional[dict]:
    if d is None or not d.rows:
        cols = [ALIASES[k][0] for k, _ in required]
        return _env(module, title, "needs_private_data", "داده‌ی داخلی متصل نشده است؛ هیچ عددی برای شرکت بورسی جایگزین نمی‌شود.",
                    [{"type": "notice", "tone": "info", "text": "یک فایل Excel/CSV یا اتصال داده را در «اتصال داده» اضافه کنید.", "missing": cols}], cols)
    missing = [f"{label} ({'/'.join(ALIASES[k][:3])})" for k, label in required if d.col(k) is None]
    if missing:
        return _env(module, title, "needs_private_data", "ستون‌های لازم در داده‌ی شما پیدا نشد.",
                    [{"type": "notice", "tone": "warning", "text": "ستون‌های زیر لازم است.", "missing": missing}], missing)
    return None


def business_kpi(d: Optional[Dataset]) -> dict:
    t = "داشبورد KPI کسب‌وکار"
    if (blk := _need("business-kpi", t, d, [("period", "دوره"), ("revenue", "فروش/درآمد")])):
        return blk
    per, rev, cost = d.values(d.col("period")), d.numbers(d.col("revenue")), d.numbers(d.col("cost"))
    series = [(str(p), r) for p, r in zip(per, rev) if r is not None]
    if len(series) < 2:
        return _env("business-kpi", t, "needs_private_data", "حداقل دو دوره با فروش معتبر لازم است.", [], ["حداقل ۲ دوره"])
    growth = [(series[i][1] - series[i - 1][1]) / abs(series[i - 1][1]) for i in range(1, len(series)) if series[i - 1][1]]
    total = sum(v for _, v in series)
    items = [{"label": "جمع فروش", "value": round(total, 2)}, {"label": "آخرین دوره", "value": series[-1][1]},
             {"label": "رشد دوره‌ای میانگین", "value": round(sum(growth) / len(growth), 4) if growth else None}]
    tc = sum(c for c in cost if c is not None) if d.col("cost") else None
    if tc is not None and total:
        items.append({"label": "حاشیه (فروش−هزینه)", "value": round((total - tc) / total, 4)})
    return _env("business-kpi", t, "ok", f"شاخص‌ها از {len(series)} دوره‌ی داده‌ی شما.", [
        {"type": "metrics", "items": items}, {"type": "line", "title": "فروش", "points": [{"x": p, "y": v} for p, v in series]}])


def campaign(d: Optional[Dataset]) -> dict:
    t = "کمپین بازاریابی"
    if (blk := _need("campaign", t, d, [("channel", "کانال/کمپین"), ("spend", "هزینه")])):
        return blk
    ch, sp, cv, rv = d.values(d.col("channel")), d.numbers(d.col("spend")), d.numbers(d.col("conversions")), d.numbers(d.col("revenue"))
    if d.col("conversions") is None and d.col("revenue") is None:
        return _env("campaign", t, "needs_private_data", "برای ارزیابی کمپین تبدیل یا فروش لازم است.", [], ["conversions یا revenue"])
    agg: dict[str, dict] = {}
    for i, c in enumerate(ch):
        a = agg.setdefault(str(c), {"spend": 0.0, "conv": 0.0, "rev": 0.0})
        a["spend"] += sp[i] or 0.0
        a["conv"] += (cv[i] or 0.0) if cv else 0.0
        a["rev"] += (rv[i] or 0.0) if rv else 0.0
    rows = [{"channel": k, "spend": round(v["spend"], 2), "conversions": v["conv"] if cv else None,
             "cpa": round(v["spend"] / v["conv"], 2) if cv and v["conv"] else None, "roas": round(v["rev"] / v["spend"], 3) if rv and v["spend"] else None} for k, v in agg.items()]
    return _env("campaign", t, "ok", f"عملکرد {len(rows)} کانال از داده‌ی شما.", [{"type": "table", "columns": ["channel", "spend", "conversions", "cpa", "roas"], "rows": rows}])


def pricing(d: Optional[Dataset]) -> dict:
    t = "قیمت‌گذاری هوشمند"
    if (blk := _need("pricing", t, d, [("price", "قیمت"), ("quantity", "تعداد فروش")])):
        return blk
    pairs = [(p, q) for p, q in zip(d.numbers(d.col("price")), d.numbers(d.col("quantity"))) if p and q and p > 0 and q > 0]
    if len(pairs) < 6 or len({p for p, _ in pairs}) < 4:
        return _env("pricing", t, "needs_private_data", "برای برآورد کشش قیمتی حداقل ۶ مشاهده با ۴ قیمت متفاوت لازم است.", [], ["حداقل ۶ مشاهده و ۴ قیمت متفاوت"])
    lx, ly = [math.log(p) for p, _ in pairs], [math.log(q) for _, q in pairs]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    sxx = sum((x - mx) ** 2 for x in lx)
    beta = sum((x - mx) * (y - my) for x, y in zip(lx, ly)) / sxx
    r = st.pearson(lx, ly) or 0.0
    advice = "تقاضا کشسان است؛ کاهش قیمت می‌تواند درآمد را بالا ببرد." if beta < -1 else "تقاضا کم‌کشش است؛ افزایش قیمت درآمد را بالا می‌برد (در بازه‌ی مشاهده‌شده)." if beta < 0 else "رابطه‌ی منفی قیمت-تقاضا دیده نمی‌شود؛ داده برای تصمیم قیمتی کافی نیست."
    return _env("pricing", t, "ok", advice, [{"type": "metrics", "items": [{"label": "کشش قیمتی", "value": round(beta, 3)}, {"label": "R²", "value": round(r * r, 3)}, {"label": "مشاهدات", "value": len(pairs)}]}],
                note="برآورد لگاریتمی ساده؛ همبستگی علیت نیست و خارج از بازه‌ی قیمت‌های مشاهده‌شده معتبر نیست.")


def unit_economics(d: Optional[Dataset]) -> dict:
    t = "Unit Economics"
    if (blk := _need("unit", t, d, [("spend", "هزینه بازاریابی"), ("new_customers", "مشتری جدید"), ("revenue", "فروش"), ("customers", "تعداد مشتری")])):
        return blk
    sp, nc, rv, cu, ch = sum(x or 0 for x in d.numbers(d.col("spend"))), sum(x or 0 for x in d.numbers(d.col("new_customers"))), sum(x or 0 for x in d.numbers(d.col("revenue"))), [x for x in d.numbers(d.col("customers")) if x], d.numbers(d.col("churned"))
    if not nc or not cu:
        return _env("unit", t, "needs_private_data", "مشتری جدید یا تعداد مشتری صفر است.", [], ["new_customers>0", "customers>0"])
    cac = sp / nc
    arpu = rv / sum(cu)  # revenue per customer-period
    items = [{"label": "CAC", "value": round(cac, 2)}, {"label": "ARPU (به ازای دوره)", "value": round(arpu, 2)}]
    churn = (sum(x or 0 for x in ch) / sum(cu)) if d.col("churned") and sum(cu) else None
    if churn:
        ltv = arpu / churn
        items += [{"label": "نرخ ریزش", "value": round(churn, 4)}, {"label": "LTV (درآمدی)", "value": round(ltv, 2)}, {"label": "LTV÷CAC", "value": round(ltv / cac, 2) if cac else None}]
    return _env("unit", t, "ok" if churn else "partial", "اقتصاد واحد از داده‌ی شما.", [{"type": "metrics", "items": items}],
                missing=[] if churn else ["ستون ریزش (churned)"], note="LTV بر پایه‌ی درآمد است، نه سود؛ برای LTV سودی ستون هزینه‌ی تحویل لازم است.")


def funnel(module: str, title: str, d: Optional[Dataset]) -> dict:
    if (blk := _need(module, title, d, [("stage", "مرحله"), ("users", "تعداد کاربر")])):
        return blk
    st_, us = d.values(d.col("stage")), d.numbers(d.col("users"))
    agg: dict[str, float] = {}
    for s, u in zip(st_, us):
        if u is not None:
            agg[str(s)] = agg.get(str(s), 0.0) + u
    seq = list(agg.items())
    if len(seq) < 2:
        return _env(module, title, "needs_private_data", "حداقل دو مرحله لازم است.", [], ["حداقل ۲ مرحله"])
    rows = [{"stage": s, "users": u, "conversionFromPrevious": (round(u / seq[i - 1][1], 4) if i and seq[i - 1][1] else None),
             "dropoff": (round(1 - u / seq[i - 1][1], 4) if i and seq[i - 1][1] else None)} for i, (s, u) in enumerate(seq)]
    worst = max((r for r in rows if r["dropoff"] is not None), key=lambda r: r["dropoff"], default=None)
    return _env(module, title, "ok", f"بیشترین ریزش در مرحله‌ی «{worst['stage']}» ({worst['dropoff']:.0%})." if worst else "قیف محاسبه شد.",
                [{"type": "table", "columns": ["stage", "users", "conversionFromPrevious", "dropoff"], "rows": rows},
                 {"type": "bars", "title": "کاربران در هر مرحله", "items": [{"label": r["stage"], "value": r["users"]} for r in rows]}],
                note="ترتیب مراحل همان ترتیب ردیف‌های داده‌ی شماست.")


def voc(d: Optional[Dataset]) -> dict:
    t = "VOC + Friction Points"
    if (blk := _need("voc", t, d, [("theme", "موضوع بازخورد"), ("score", "امتیاز/رضایت")])):
        return blk
    th, sc = d.values(d.col("theme")), d.numbers(d.col("score"))
    agg: dict[str, list] = {}
    for a, b in zip(th, sc):
        if b is not None:
            agg.setdefault(str(a), []).append(b)
    rows = sorted(({"theme": k, "count": len(v), "avgScore": round(sum(v) / len(v), 3)} for k, v in agg.items()), key=lambda r: r["avgScore"])
    return _env("voc", t, "ok", f"{len(rows)} موضوع؛ کم‌امتیازترین‌ها اول نمایش داده می‌شوند.", [{"type": "table", "columns": ["theme", "count", "avgScore"], "rows": rows}],
                note="تحلیل متنی آزاد (NLP) فعال نیست؛ فقط موضوع/امتیاز ثبت‌شده توسط شما تجمیع می‌شود.")


def governance(kpis: list[dict]) -> dict:
    t = "KPI Governance"
    if not kpis:
        return _env("governance", t, "needs_private_data", "هنوز شاخصی ثبت نشده است.", [{"type": "notice", "tone": "info", "text": "نام، مالک، هدف و چرخه‌ی هر شاخص را ثبت کنید.", "missing": ["name", "owner", "target", "cadence"]}], ["حداقل یک شاخص"])
    rows = []
    for k in kpis:
        att = (k["current_value"] / k["target"]) if k.get("current_value") is not None and k.get("target") else None
        rows.append({"name": k["name"], "owner": k.get("owner"), "target": k.get("target"), "current": k.get("current_value"), "attainment": round(att, 3) if att is not None else None, "cadence": k.get("cadence")})
    no_owner = [r["name"] for r in rows if not r["owner"]]
    return _env("governance", t, "ok" if not no_owner else "partial", f"{len(rows)} شاخص ثبت شده است.", [{"type": "table", "columns": ["name", "owner", "target", "current", "attainment", "cadence"], "rows": rows}],
                missing=[f"مالک: {n}" for n in no_owner])


def plan(d: Optional[Dataset], kpis: list[dict]) -> dict:
    t = "Business Plan"
    checks = [("داده‌ی فروش/درآمد", bool(d and d.col("revenue"))), ("هزینه", bool(d and d.col("cost"))), ("اقتصاد واحد", bool(d and d.col("spend") and d.col("new_customers"))), ("شاخص‌های ثبت‌شده", bool(kpis))]
    if not any(ok for _, ok in checks):
        return _env("plan", t, "needs_private_data", "طرح کسب‌وکار از داده‌ی داخلی ساخته می‌شود و هنوز داده‌ای متصل نیست.", [], [n for n, _ in checks])
    blocks = [{"type": "table", "title": "آمادگی بخش‌های طرح", "columns": ["section", "ready"], "rows": [{"section": n, "ready": "بله" if ok else "خیر"} for n, ok in checks]}]
    kp = business_kpi(d) if d and d.col("revenue") and d.col("period") else None
    if kp and kp["status"] == "ok":
        blocks += kp["blocks"]
    return _env("plan", t, "partial" if not all(ok for _, ok in checks) else "ok", "پیش‌نویس ساختاریافته از داده‌ی خودتان؛ بخش‌های بدون داده خالی می‌مانند.", blocks, [n for n, ok in checks if not ok])


def compute(module: str, dataset: Optional[dict], kpis: list[dict]) -> dict:
    d = Dataset(dataset) if dataset else None
    if module == "business-kpi":
        return business_kpi(d)
    if module == "campaign":
        return campaign(d)
    if module == "pricing":
        return pricing(d)
    if module == "unit":
        return unit_economics(d)
    if module == "behavior":
        return funnel("behavior", "رفتار کاربر", d)
    if module == "journey":
        return funnel("journey", "Journey Map", d)
    if module == "voc":
        return voc(d)
    if module == "governance":
        return governance(kpis)
    if module == "plan":
        return plan(d, kpis)
    raise KeyError(module)
