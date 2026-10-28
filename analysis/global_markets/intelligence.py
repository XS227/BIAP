"""Read-only company intelligence over an existing BIAP Global analysis payload.

This deliberately does not call an LLM, enrich financial statements, rank stocks,
alter any agent scores, or write to caches. It exposes an auditable foundation
for a future conversational analyst without pretending that partial evidence is
verified field by field.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

# (field, English title, Persian title, unit family, data scope)
_METRICS = (
    ("price", "Last price", "آخرین قیمت", "listing_currency", "market"),
    ("market_cap", "Market capitalization", "ارزش بازار", "listing_currency", "market"),
    ("return_3m_pct", "3-month return", "بازده سه‌ماهه", "percent", "market"),
    ("volatility_annualized_pct", "Annualized volatility", "نوسان سالانه", "percent", "market"),
    ("pe", "P/E", "نسبت قیمت به سود", "multiple", "market"),
    ("pb", "P/B", "نسبت قیمت به ارزش دفتری", "multiple", "market"),
    ("revenue", "Revenue", "درآمد", "reporting_currency", "fundamental"),
    ("revenue_prev", "Prior revenue", "درآمد دوره قبل", "reporting_currency", "fundamental"),
    ("revenue_yoy_pct", "Revenue growth", "رشد درآمد", "percent", "fundamental"),
    ("net_income", "Net income", "سود خالص", "reporting_currency", "fundamental"),
    ("net_margin_pct", "Net margin", "حاشیه سود خالص", "percent", "fundamental"),
    ("operating_cash_flow", "Operating cash flow", "جریان نقد عملیاتی", "reporting_currency", "fundamental"),
    ("free_cash_flow", "Free cash flow", "جریان نقد آزاد", "reporting_currency", "fundamental"),
    ("cash_and_equivalents", "Cash and equivalents", "نقد و معادل نقد", "reporting_currency", "fundamental"),
    ("total_debt", "Total debt", "کل بدهی مالی", "reporting_currency", "fundamental"),
    ("total_assets", "Total assets", "کل دارایی‌ها", "reporting_currency", "fundamental"),
    ("total_equity", "Total equity", "حقوق صاحبان سهام", "reporting_currency", "fundamental"),
)

_TOPIC_RULES = (
    ("recommendation", ("خرید", "بخر", "فروش", "بفروش", "buy", "sell", "recommendation", "سرمایه‌گذاری")),
    ("sources", ("منبع", "منابع", "مدرک", "مستند", "افشا", "source", "evidence", "filing", "audit")),
    ("risk", ("ریسک", "ورشکستگی", "اعتبار", "risk", "distress", "default")),
    ("cash_flow", ("جریان نقد", "جریان وجوه", "cash flow", "cashflow")),
    ("margin", ("حاشیه سود", "margin", "profitability")),
    ("net_income", ("سود خالص", "سودآوری", "net income", "net profit")),
    ("revenue", ("درآمد", "فروش", "revenue", "sales", "growth")),
    ("debt", ("بدهی", "اهرم", "debt", "leverage")),
    ("cash", ("نقدینگی", "وجه نقد", "موجودی نقد", "cash", "liquidity")),
    ("valuation", ("ارزش‌گذاری", "قیمت به سود", "p/e", "p/b", "valuation", "multiple")),
)

_TOPIC_KEYS = {
    "revenue": ("revenue", "revenue_prev", "revenue_yoy_pct"),
    "net_income": ("net_income", "net_margin_pct"),
    "margin": ("net_margin_pct", "net_income"),
    "debt": ("total_debt", "total_equity"),
    "cash": ("cash_and_equivalents", "operating_cash_flow"),
    "cash_flow": ("operating_cash_flow", "free_cash_flow"),
    "valuation": ("pe", "pb", "market_cap"),
}


def _number(value: Any) -> float | int | None:
    if type(value) not in (float, int):
        return None
    try:
        return value if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _safe_sources(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [
        {
            "provider": source.get("provider"),
            "sourceType": source.get("source_type"),
            "sourceUrl": source.get("source_url"),
            "periodEnd": source.get("period_end"),
            "observedAt": source.get("observed_at"),
            "auditStatus": source.get("audit_status", "unknown"),
        }
        for source in raw[:25] if isinstance(source, dict)
    ]


def build_company_dashboard(analysis: dict) -> dict:
    """Compose snapshot KPIs and evidence labels without recalculating a call."""
    company = analysis.get("company") or {}
    filing = analysis.get("fundamentalEvidence") or {}
    evidence = analysis.get("evidence") or {}
    fundamentals = filing.get("values") or {}
    listing_currency = company.get("currency") or analysis.get("currency")
    reporting_currency = company.get("reporting_currency") or fundamentals.get("reporting_currency")
    period = filing.get("reportPeriod")
    official_status = filing.get("officialStatus") or "UNKNOWN"
    metrics = []
    for key, en, fa, unit_family, scope in _METRICS:
        raw_value = fundamentals.get(key) if scope == "fundamental" else company.get(key)
        value = _number(raw_value)
        unit = (
            reporting_currency if unit_family == "reporting_currency"
            else listing_currency if unit_family == "listing_currency"
            else "%" if unit_family == "percent" else "x"
        )
        metrics.append({
            "key": key,
            "labelEn": en,
            "labelFa": fa,
            "value": value,
            "available": value is not None,
            "unit": unit,
            "scope": scope,
            "asOf": period if scope == "fundamental" else company.get("price_observed_at"),
            # A company-level official filing does not imply individual fields
            # were not supplemented from a vendor during normalization.
            "fieldVerified": False,
            "sourceClass": (
                "normalized_fundamentals_not_field_verified" if scope == "fundamental"
                else "normalized_market_not_field_verified"
            ),
        })
    return {
        "mode": "read_only_research_preview",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "identity": {
            key: analysis.get(key) for key in
            ("country", "exchange", "mic", "ticker", "name", "isin", "lei", "currency")
        },
        "decision": {
            "existingCall": analysis.get("call"),
            "score": _number(analysis.get("score")),
            "confidence": _number(analysis.get("confidence")),
            "unchanged": True,
        },
        "evidence": {
            "status": evidence.get("status", "UNKNOWN"),
            "missingCritical": evidence.get("missing_critical") or [],
            "contradictions": evidence.get("contradictions") or [],
            "officialStatus": official_status,
            "filingIsOfficial": bool(filing.get("isOfficial")),
            "reportPeriod": period,
            "filingDate": filing.get("filingDate"),
            "priceObservedAt": company.get("price_observed_at"),
            "sourceUrl": filing.get("sourceUrl"),
            "sourceProvider": filing.get("sourceProvider"),
            "auditStatus": filing.get("auditStatus"),
            "freshnessTier": filing.get("freshnessTier"),
            "limitations": filing.get("limitations") or [],
        },
        "risk": {
            "distressStatus": (analysis.get("distress") or {}).get("status"),
            "positiveBlock": (analysis.get("distress") or {}).get("positive_block"),
        },
        "metrics": metrics,
        "agentSignals": [
            {key: row.get(key) for key in ("agent", "vote", "confidence", "reasoning")}
            for row in (analysis.get("signals") or []) if isinstance(row, dict)
        ],
        "sources": _safe_sources(company.get("sources")),
        "limitations": [
            "A company-level official filing is not field-level verification; some normalized fields may be vendor supplements.",
            "Annual financial periods and market-price timestamps differ; compare only like-for-like currencies and periods.",
            "This read-only dashboard is not an investment recommendation, a forecast, or an ERP integration.",
        ],
    }


def _display_metric(metric: dict | None, language: str) -> str:
    if not metric or not metric["available"]:
        return "داده موجود نیست" if language == "fa" else "Unavailable"
    value = metric["value"]
    text = f"{value:,.4f}".rstrip("0").rstrip(".") if not float(value).is_integer() else f"{value:,.0f}"
    unit = metric.get("unit") or ""
    return f"{text} {unit}".strip()


def answer_company_question(dashboard: dict, question: str, language: str = "fa") -> dict:
    """Grounded, deterministic FAQ on one selected company's analysis only."""
    lang = "en" if language == "en" else "fa"
    normalized = re.sub(r"\s+", " ", question.strip().lower().replace("ي", "ی").replace("ك", "ک"))
    topics = [topic for topic, patterns in _TOPIC_RULES if any(word in normalized for word in patterns)]
    metrics = {metric["key"]: metric for metric in dashboard["metrics"]}
    evidence = dashboard["evidence"]
    details: list[str] = []
    for topic in topics[:4]:
        if topic in _TOPIC_KEYS:
            for key in _TOPIC_KEYS[topic]:
                metric = metrics[key]
                label = metric["labelEn"] if lang == "en" else metric["labelFa"]
                details.append(f"{label}: {_display_metric(metric, lang)}")
        elif topic == "risk":
            if lang == "fa":
                details.append(f"وضعیت شواهد: {evidence['status']}؛ وضعیت ریسک مالی: {dashboard['risk']['distressStatus'] or 'نامشخص'}")
            else:
                details.append(f"Evidence: {evidence['status']}; financial distress: {dashboard['risk']['distressStatus'] or 'unknown'}")
        elif topic == "sources":
            url = evidence.get("sourceUrl") or ("در دسترس نیست" if lang == "fa" else "Unavailable")
            details.append(("منبع گزارش: " if lang == "fa" else "Filing source: ") + url)
            details.append(("وضعیت رسمی: " if lang == "fa" else "Official filing status: ") + evidence["officialStatus"])
        elif topic == "recommendation":
            call = dashboard["decision"]["existingCall"] or "NO_RECOMMENDATION"
            details.append(("خروجی بدون تغییر موتور اصلی BIAP: " if lang == "fa" else "Unchanged BIAP decision: ") + call)

    period = evidence.get("reportPeriod") or ("نامشخص" if lang == "fa" else "unknown")
    status = evidence["officialStatus"]
    if details:
        note = (
            f"دوره گزارش: {period}؛ وضعیت منبع رسمی: {status}. اعداد از خروجی نرمال‌شده BIAP هستند "
            "و صحت تک‌تک فیلدها مستقلاً تأیید نشده است."
            if lang == "fa" else
            f"Filing period: {period}; official status: {status}. Figures come from BIAP normalized data "
            "and have not been individually field-verified."
        )
        response = "\n".join(details) + "\n" + note
        supported = True
    else:
        response = (
            "در این نسخه پرسش‌هایی درباره درآمد، سود، بدهی، نقدینگی، ریسک، ارزش‌گذاری، منابع و تصمیم ثبت‌شده پشتیبانی می‌شوند."
            if lang == "fa" else
            "This preview supports questions on revenue, profit, debt, cash, risk, valuation, sources and the existing decision."
        )
        supported = False
    return {
        "answer": response,
        "language": lang,
        "supported": supported,
        "matchedTopics": topics[:4],
        "method": "deterministic_grounded_preview",
        "generativeModelUsed": False,
        "readOnly": True,
        "identity": dashboard["identity"],
        "evidence": evidence,
    }
