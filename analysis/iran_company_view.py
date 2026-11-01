"""Read-only Iranian company views built from STORED BIAP data.

Sources (all already persisted by other jobs; nothing here recomputes, fetches, or writes them):
  * listed_companies.sqlite3  -> identity, price snapshot (with provenance), CODAL statements
  * biap_performance.sqlite3  -> the latest stored Kiasha run with its seven agents

Three products: ``company_view``, ``audit_checks`` and ``ai_report`` (LLM, cached per company per day,
rate-limited per user). A missing input is reported as missing (``INSUFFICIENT_DATA``); no figure is invented.
The seven Iranian agents keep their own names and are never merged with Global's six.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

INSUFFICIENT = "INSUFFICIENT_DATA"
IRAN_AGENTS = ("fundamental", "risk", "forecast", "technical", "comparison", "flow", "scenario")
LOW_CONFIDENCE = 0.30
PRICE_STALE_DAYS = 3
DISCLAIMER_FA = "تولیدشده با هوش مصنوعی؛ توصیه‌ی سرمایه‌گذاری نیست."
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_HERE = Path(__file__).resolve().parent


class NotFound(LookupError):
    pass


class RateLimited(RuntimeError):
    pass


class AIUnavailable(RuntimeError):
    pass


def normalize_fa(value: Any) -> str:
    """Fold Arabic/Persian letter and digit variants so 'پکرمان' == 'پكرمان' and '۲۳۲۱' == '2321'."""
    text = str(value or "").translate(_DIGITS)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ").replace("‏", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _div(a: Any, b: Any) -> Optional[float]:
    x, y = _num(a), _num(b)
    return None if x is None or y is None or y == 0 else x / y


def _round(v: Optional[float], d: int = 4) -> Optional[float]:
    return None if v is None else round(v, d)


def _iso(ts: Any) -> Optional[str]:
    n = _num(ts)
    if n is None or n <= 0:
        return None
    return datetime.fromtimestamp(n, timezone.utc).isoformat()


def _parse_dt(value: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _paths() -> tuple[str, str]:
    return (os.environ.get("BIAP_LISTED_COMPANY_DB") or str(_HERE / "listed_companies.sqlite3"),
            os.environ.get("BIAP_PERFORMANCE_DB") or str(_HERE / "biap_performance.sqlite3"))


def _ro(path: str) -> sqlite3.Connection:
    if not Path(path).exists():
        raise NotFound(f"database not found: {Path(path).name}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- lookup
def resolve(query: str) -> sqlite3.Row:
    """Find one listed company by TSETMC instrument code or by symbol (Persian/Arabic letter and digit variants)."""
    q = normalize_fa(query)
    if not q or len(q) > 64:
        raise ValueError("invalid query")
    conn = _ro(_paths()[0])
    try:
        rows = conn.execute("SELECT * FROM listed_companies").fetchall() if not q.isdigit() else \
            conn.execute("SELECT * FROM listed_companies WHERE code=?", (q,)).fetchall()
    finally:
        conn.close()
    exact = [r for r in rows if normalize_fa(r["code"]) == q or normalize_fa(r["symbol"]) == q]
    if not exact:
        raise NotFound(f"شرکتی با این نماد یا کد پیدا نشد: {query}")
    # prefer the row that carries an enrichment payload, then the shortest/primary symbol
    exact.sort(key=lambda r: (r["company_json"] is None, r["code"] != q and not q.isdigit() and not str(r["code"]).isdigit(), len(str(r["symbol"] or ""))))
    return exact[0]


def _latest_kiasha(code: str, symbol: str) -> Optional[dict]:
    try:
        conn = _ro(_paths()[1])
    except NotFound:
        return None
    try:
        want = {normalize_fa(code), normalize_fa(symbol)}
        row = conn.execute(
            "SELECT id, code, symbol, generated_at, reference_price, kiasha_call, weighted_score, payload_json "
            "FROM recommendation_observations WHERE code=? ORDER BY generated_at DESC LIMIT 1", (str(code),)).fetchone()
        if row is None:
            for r in conn.execute("SELECT id, code, symbol, generated_at, reference_price, kiasha_call, weighted_score, payload_json "
                                  "FROM recommendation_observations ORDER BY generated_at DESC LIMIT 20000"):
                if normalize_fa(r["symbol"]) in want or normalize_fa(r["code"]) in want:
                    row = r
                    break
    finally:
        conn.close()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except ValueError:
        payload = {}
    return {"id": row["id"], "generatedAt": row["generated_at"], "referencePrice": row["reference_price"],
            "call": row["kiasha_call"], "score": row["weighted_score"], "breakdown": payload.get("breakdown") or []}


# --------------------------------------------------------------------------- statements
def _period_from_title(title: Any) -> Optional[str]:
    m = re.search(r"(\d{4}/\d{2}/\d{2})", str(title or "").translate(_DIGITS))
    return m.group(1) if m else None


def _stmt(codal: dict) -> dict:
    """Normalise the stored CODAL fundamentals; keys absent from the stored record stay None."""
    g = lambda k: _num(codal.get(k))  # noqa: E731
    return {
        "revenue": g("revenue_current"), "revenue_prev": g("revenue_prev"),
        "gross_profit": g("gross_profit_current"), "gross_profit_prev": g("gross_profit_prev"),
        "net_income": g("net_profit_current"), "net_income_prev": g("net_profit_prev"),
        "total_assets": g("total_assets_current"), "total_assets_prev": g("total_assets_prev"),
        "total_liabilities": g("total_liabilities_current"), "total_liabilities_prev": g("total_liabilities_prev"),
        "total_equity": g("total_equity_current"), "total_equity_prev": g("total_equity_prev"),
        "operating_cash_flow": g("operating_cash_flow_current"), "current_assets": g("current_assets_current"),
        "current_liabilities": g("current_liabilities_current"), "retained_earnings": g("retained_earnings_current"),
        "operating_income": g("operating_income_current"),
    }


STATEMENT_LABELS = (
    ("revenue", "درآمد عملیاتی"), ("revenue_prev", "درآمد دوره‌ی قبل"), ("gross_profit", "سود ناخالص"),
    ("operating_income", "سود عملیاتی"), ("net_income", "سود خالص"), ("net_income_prev", "سود خالص دوره‌ی قبل"),
    ("operating_cash_flow", "جریان نقد عملیاتی"), ("total_assets", "جمع دارایی‌ها"), ("current_assets", "دارایی‌های جاری"),
    ("total_liabilities", "جمع بدهی‌ها"), ("current_liabilities", "بدهی‌های جاری"), ("total_equity", "حقوق صاحبان سهام"),
    ("retained_earnings", "سود انباشته"),
)


def _ratios(s: dict) -> dict:
    def r(label: str, num: str, den: str, pct: bool = False) -> dict:
        v = _div(s.get(num), s.get(den))
        miss = [k for k in (num, den) if _num(s.get(k)) is None]
        return {"label": label, "value": _round(v * 100 if (v is not None and pct) else v), "unit": "%" if pct else "x",
                "formula": f"{num} / {den}", "missing": miss if v is None else []}
    growth = _div(s.get("revenue"), s.get("revenue_prev"))
    return {
        "net_margin": r("حاشیه سود خالص", "net_income", "revenue", True),
        "gross_margin": r("حاشیه سود ناخالص", "gross_profit", "revenue", True),
        "roa": r("بازده دارایی‌ها", "net_income", "total_assets", True),
        "roe": r("بازده حقوق صاحبان سهام", "net_income", "total_equity", True),
        "liabilities_to_equity": r("بدهی به حقوق صاحبان سهام", "total_liabilities", "total_equity"),
        "liabilities_to_assets": r("بدهی به دارایی", "total_liabilities", "total_assets"),
        "current_ratio": r("نسبت جاری", "current_assets", "current_liabilities"),
        "revenue_growth": {"label": "رشد درآمد", "value": _round((growth - 1) * 100) if growth is not None else None, "unit": "%",
                           "formula": "revenue / revenue_prev - 1",
                           "missing": [] if growth is not None else [k for k in ("revenue", "revenue_prev") if _num(s.get(k)) is None]},
    }


def _price_block(company: dict, enriched_at: Optional[str], kiasha: Optional[dict], now: datetime) -> dict:
    m = company.get("market") or {}
    price = _num(m.get("price") if m.get("price") is not None else m.get("last_price"))
    observed = m.get("price_observed_at") or _iso(m.get("quote_fetched_at")) or enriched_at
    dt = _parse_dt(observed)
    age = None if dt is None else round((now - dt).total_seconds() / 86400, 1)
    source = m.get("price_source") or m.get("valuation_source") or ("tsetmc_instrument_info" if price is not None else None)
    if price is None:
        status = "MISSING"
    elif age is None:
        status = "UNKNOWN_AGE"
    elif age > PRICE_STALE_DAYS:
        status = "STALE"
    else:
        status = "VERIFIED"
    block = {"price": price, "observedAt": observed, "ageDays": age, "source": source, "status": status,
             "provenance": "company-record-snapshot"}
    if kiasha and kiasha.get("referencePrice") is not None:
        block["kiashaReferencePrice"] = kiasha["referencePrice"]
        block["kiashaReferenceAt"] = kiasha["generatedAt"]
        ref = _num(kiasha["referencePrice"])
        block["conflictsWithKiasha"] = bool(price and ref and abs(price - ref) / ref > 0.02 and
                                            (dt is None or (_parse_dt(kiasha["generatedAt"]) or now) > dt))
    return block


def _agents(kiasha: Optional[dict]) -> list[dict]:
    by = {str(b.get("agent")): b for b in (kiasha or {}).get("breakdown", []) if isinstance(b, dict)}
    out = []
    for name in IRAN_AGENTS:
        b = by.get(name)
        vote, conf = (_num(b.get("vote")), _num(b.get("confidence"))) if b else (None, None)
        if b is None or vote is None or conf is None:
            status = "MISSING"
        elif conf <= 0.0:
            status = "NO_DATA"       # agent ran but had no verified input (confidence 0): its vote is not evidence
        elif conf < LOW_CONFIDENCE:
            status = "LOW_CONFIDENCE"
        else:
            status = "OK"
        out.append({"agent": name, "vote": vote, "confidence": conf, "dataStatus": status,
                    "reasoning": (b or {}).get("reasoning"), "weight": _num((b or {}).get("weight_normalized")),
                    "observedSamples": (b or {}).get("observed_samples")})
    return out


def company_view(query: str, *, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    row = resolve(query)
    company = json.loads(row["company_json"]) if row["company_json"] else {}
    codal = company.get("codal") or {}
    s = _stmt(codal)
    kiasha = _latest_kiasha(row["code"], row["symbol"])
    agents = _agents(kiasha)
    # CODAL metadata alone is not a verified numeric financial statement.
    have_fund = any(value is not None for value in s.values())
    warnings: list[str] = []
    if not have_fund:
        if codal:
            warnings.append("فراداده گزارش کدال موجود است، اما ارقام صورت‌های مالی قابل اتکا ذخیره نشده‌اند.")
        else:
            warnings.append("صورت‌های مالی کدال برای این شرکت ذخیره نشده است؛ تحلیل بنیادی کامل نیست.")
    fund_agent = next(a for a in agents if a["agent"] == "fundamental")
    if fund_agent["dataStatus"] in ("NO_DATA", "MISSING"):
        warnings.append("عامل بنیادی داده‌ی معتبر نداشته است؛ رأی آن شاهد محسوب نمی‌شود.")
    if kiasha is None:
        warnings.append("نتیجه‌ی ذخیره‌شده‌ای از کیاشا برای این شرکت وجود ندارد.")
    price = _price_block(company, row["enriched_at"], kiasha, now)
    if price["status"] in ("STALE", "MISSING", "UNKNOWN_AGE"):
        warnings.append({"STALE": "قیمت ذخیره‌شده‌ی رکورد شرکت کهنه است.", "MISSING": "قیمتی ذخیره نشده است.",
                         "UNKNOWN_AGE": "زمان قیمت ذخیره‌شده نامشخص است."}[price["status"]])
    if price.get("conflictsWithKiasha"):
        warnings.append("قیمت رکورد شرکت با قیمت مرجع آخرین تحلیل کیاشا تفاوت دارد؛ هر دو با زمان نمایش داده شده‌اند.")
    diag = ((company.get("data_diagnostics") or {}).get("codal") or {})
    return {
        "source": "stored-company-db",
        "identity": {"code": row["code"], "symbol": row["symbol"], "nameFa": row["name_fa"], "market": row["market"],
                     "sector": (company.get("market") or {}).get("sector_name")},
        "recordEnrichedAt": row["enriched_at"], "recordUpdatedAt": row["updated_at"],
        "price": price,
        "agents": agents,
        "kiasha": None if kiasha is None else {"call": kiasha["call"], "score": kiasha["score"], "generatedAt": kiasha["generatedAt"],
                                                "referencePrice": kiasha["referencePrice"], "observationId": kiasha["id"]},
        "dataQualityWarnings": warnings,
        "financials": {
            "available": have_fund,
            "reportTitle": codal.get("report_title"), "reportPeriod": _period_from_title(codal.get("report_title")),
            "scope": codal.get("report_scope"), "tracingNo": codal.get("tracing_no"), "sourceUrl": codal.get("report_url"),
            "source": codal.get("source"), "auditOpinion": codal.get("audit_opinion"),
            "statements": [{"key": k, "label": label, "value": s.get(k)} for k, label in STATEMENT_LABELS],
            "ratios": _ratios(s),
            "missingReason": None if have_fund else (diag.get("fundamentalsReason") or diag.get("metadataError") or ("CODAL metadata present, but no numeric statements verified" if codal else "no CODAL statements stored")),
            "lastUpdate": row["enriched_at"],
        },
        "distress": company.get("distress"),
    }


# --------------------------------------------------------------------------- audit checks
def _check(cid: str, title: str, status: str, inputs: dict, *, value: Any = None, detail: str = "", missing: Optional[list] = None,
           period: Optional[str] = None, source: Optional[str] = None) -> dict:
    return {"id": cid, "title": title, "status": status, "value": value, "detail": detail, "inputs": inputs,
            "missing": missing or [], "period": period, "source": source}


def audit_checks(query: str) -> dict:
    row = resolve(query)
    company = json.loads(row["company_json"]) if row["company_json"] else {}
    codal = company.get("codal") or {}
    s = _stmt(codal)
    period = _period_from_title(codal.get("report_title"))
    src = codal.get("source") or ("codal" if codal else None)
    miss = lambda keys: [k for k in keys if s.get(k) is None]  # noqa: E731
    pick = lambda keys: {k: s.get(k) for k in keys}  # noqa: E731
    checks: list[dict] = []

    need = ["net_income", "operating_cash_flow", "total_assets"]
    if miss(need) or not s["total_assets"]:
        checks.append(_check("accruals", "کیفیت سود / اقلام تعهدی", INSUFFICIENT, pick(need), missing=miss(need), period=period, source=src,
                             detail="(سود خالص − جریان نقد عملیاتی) / جمع دارایی‌ها"))
    else:
        acc = (s["net_income"] - s["operating_cash_flow"]) / s["total_assets"]
        checks.append(_check("accruals", "کیفیت سود / اقلام تعهدی", "RED_FLAG" if acc > 0.10 else "WATCH" if acc > 0.05 else "PASS",
                             pick(need), value=_round(acc), period=period, source=src, detail="بیش از ۰٫۰۵ هشدار؛ بیش از ۰٫۱۰ پرچم قرمز"))

    need = ["net_income", "operating_cash_flow"]
    if miss(need):
        checks.append(_check("cash_divergence", "واگرایی سود و جریان نقد عملیاتی", INSUFFICIENT, pick(need), missing=miss(need), period=period, source=src))
    else:
        ni, ocf = s["net_income"], s["operating_cash_flow"]
        if ni > 0 and ocf < 0:
            st, v = "RED_FLAG", None
        elif ni > 0:
            v = ocf / ni
            st = "RED_FLAG" if v < 0.5 else "WATCH" if v < 0.8 else "PASS"
        else:
            st, v = "NOT_APPLICABLE", None
        checks.append(_check("cash_divergence", "واگرایی سود و جریان نقد عملیاتی", st, pick(need), value=_round(v), period=period, source=src))

    bene = ["revenue", "revenue_prev", "total_assets", "total_assets_prev", "net_income", "operating_cash_flow"]
    checks.append(_check("beneish_m", "امتیاز بنیش (Beneish M)", INSUFFICIENT, pick(bene),
                         missing=miss(bene) + ["receivables", "cogs", "sga", "ppe", "depreciation", "long_term_debt"],
                         period=period, source=src,
                         detail="محاسبه‌ی بنیش به حساب‌های دریافتنی، بهای تمام‌شده، هزینه‌های عمومی، دارایی ثابت، استهلاک و بدهی بلندمدت دو دوره نیاز دارد که در داده‌ی ذخیره‌شده نیست."))

    z_in = ["current_assets", "current_liabilities", "retained_earnings", "operating_income", "total_equity", "total_assets", "total_liabilities"]
    if miss(z_in) or not s["total_assets"] or not s["total_liabilities"]:
        checks.append(_check("altman_z", "آلتمن Z″ (تداوم فعالیت)", INSUFFICIENT, pick(z_in), missing=miss(z_in), period=period, source=src))
    else:
        ta, tl = s["total_assets"], s["total_liabilities"]
        z = 6.56 * (s["current_assets"] - s["current_liabilities"]) / ta + 3.26 * s["retained_earnings"] / ta + 6.72 * s["operating_income"] / ta + 1.05 * s["total_equity"] / tl
        checks.append(_check("altman_z", "آلتمن Z″ (تداوم فعالیت)", "PASS" if z > 2.6 else "WATCH" if z >= 1.1 else "RED_FLAG", pick(z_in),
                             value=_round(z, 3), period=period, source=src, detail="بیش از ۲٫۶ ایمن؛ ۱٫۱ تا ۲٫۶ خاکستری؛ کمتر از ۱٫۱ پریشانی"))

    zm_in = ["net_income", "total_assets", "total_liabilities", "current_assets", "current_liabilities"]
    if miss(zm_in) or not s["total_assets"] or not s["current_liabilities"]:
        checks.append(_check("zmijewski", "زمیجوسکی (احتمال ورشکستگی)", INSUFFICIENT, pick(zm_in), missing=miss(zm_in), period=period, source=src))
    else:
        x = -4.336 - 4.513 * s["net_income"] / s["total_assets"] + 5.679 * s["total_liabilities"] / s["total_assets"] + 0.004 * s["current_assets"] / s["current_liabilities"]
        p = 1 / (1 + math.exp(-x))
        checks.append(_check("zmijewski", "زمیجوسکی (احتمال ورشکستگی)", "RED_FLAG" if p >= 0.5 else "WATCH" if p >= 0.25 else "PASS",
                             pick(zm_in), value=_round(p, 3), period=period, source=src))

    op = codal.get("audit_opinion")
    if op:
        low = str(op).lower()
        st = "PASS" if any(w in low for w in ("مقبول", "unqualified")) and "مشروط" not in low else \
            "RED_FLAG" if any(w in low for w in ("مشروط", "مردود", "عدم اظهارنظر", "adverse", "disclaimer", "qualified")) else "WATCH"
        checks.append(_check("auditor_opinion", "اظهارنظر حسابرس", st, {"audit_opinion": str(op)}, value=str(op), period=period, source=src))
    else:
        checks.append(_check("auditor_opinion", "اظهارنظر حسابرس", INSUFFICIENT, {"audit_opinion": None}, missing=["audit_opinion"], period=period, source=src,
                             detail="اظهارنظر حسابرس در داده‌ی ذخیره‌شده نیست."))
    return {"source": "stored-company-db",
            "identity": {"code": row["code"], "symbol": row["symbol"], "nameFa": row["name_fa"]},
            "reportPeriod": period, "provider": src, "lastUpdate": row["enriched_at"], "financialsAvailable": bool(codal),
            "checks": checks,
            "summary": {"redFlags": [c["id"] for c in checks if c["status"] == "RED_FLAG"],
                        "insufficient": [c["id"] for c in checks if c["status"] == INSUFFICIENT],
                        "note": "غربالگری قطعی روی صورت‌های مالی ذخیره‌شده برای بررسی انسانی؛ اظهارنظر حسابرسی نیست."}}


# --------------------------------------------------------------------------- AI report (cache + per-user limit)
USER_DAILY_LIMIT = int(os.environ.get("BIAP_AI_REPORT_USER_DAILY_LIMIT", "10"))
GLOBAL_DAILY_CAP = int(os.environ.get("BIAP_AI_REPORT_GLOBAL_DAILY_CAP", "300"))
_lock = threading.Lock()


def _ai_db() -> sqlite3.Connection:
    path = os.environ.get("BIAP_IRAN_AI_REPORT_DB", "").strip()
    if not path:
        raise AIUnavailable("Isolated development AI cache path is not configured.")
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS report (key TEXT PRIMARY KEY, day TEXT, body TEXT, model TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS usage (client TEXT, day TEXT, n INTEGER, PRIMARY KEY (client, day))")
    return conn


def _prompt(view: dict, audit: dict, day: str) -> str:
    payload = {"identity": view["identity"], "price": view["price"], "agents": view["agents"], "kiasha": view["kiasha"],
               "dataQualityWarnings": view["dataQualityWarnings"],
               "financials": {k: view["financials"][k] for k in ("available", "reportPeriod", "statements", "ratios", "missingReason", "lastUpdate")},
               "auditChecks": [{k: c[k] for k in ("id", "status", "value", "missing")} for c in audit["checks"]]}
    return ("You write a short PERSIAN (Farsi) company analysis for a retail research app. Use ONLY the JSON below (stored BIAP data). "
            "Do not use outside knowledge, do not invent numbers, and do not give a BUY/SELL recommendation or a price target; "
            "quote Kiasha's stored result and its timestamp exactly. If fundamentals are missing say the analysis is not a full fundamental analysis. "
            "Use exactly these markdown sections: ## نقاط قوت, ## نقاط ضعف, ## ریسک‌های اصلی, ## داده‌های ناموجود. "
            "Each has 2-5 short bullets; if nothing in the data supports a section write 'داده کافی نیست'. "
            f"Date: {day}.\n\nDATA:\n" + json.dumps(payload, ensure_ascii=False, default=str))


def _call_llm(prompt: str) -> tuple[str, str]:
    import httpx

    from urllib.parse import urlsplit

    proxy = os.environ.get("BIAP_AI_PROXY_URL", "").rstrip("/")
    model = os.environ.get("BIAP_AI_REPORT_MODEL") or os.environ.get("KIASHA_AI_MODEL", "claude-sonnet-5")
    # The checkpoint must use the configured BIAP proxy, never a direct
    # Anthropic/OpenAI fallback. The proxy owns its own credentials.
    try:
        target = urlsplit(proxy)
        hostname = (target.hostname or "").lower()
        loopback = hostname in ("127.0.0.1", "::1", "localhost")
        valid = (target.scheme == "https" or (target.scheme == "http" and loopback)) and bool(hostname)
        valid = valid and not target.username and not target.password and not target.query and not target.fragment
        valid = valid and hostname not in ("api.anthropic.com", "api.openai.com")
    except ValueError:
        valid = False
    if not valid:
        raise AIUnavailable("BIAP AI proxy is not configured with an approved HTTPS or loopback URL.")
    headers = {"content-type": "application/json", "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01")}
    try:
        resp = httpx.post(f"{proxy}/messages", headers=headers, timeout=45,
                          json={"model": model, "max_tokens": 900, "messages": [{"role": "user", "content": prompt}]})
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"سرویس هوش مصنوعی در دسترس نیست ({type(exc).__name__})") from exc
    if resp.status_code != 200:
        raise AIUnavailable(f"سرویس هوش مصنوعی خطای HTTP {resp.status_code} داد")
    text = "".join(p.get("text", "") for p in (resp.json().get("content") or []) if isinstance(p, dict)).strip()
    if not text:
        raise AIUnavailable("سرویس هوش مصنوعی گزارش خالی برگرداند")
    return text, model


def ai_report(query: str, user_id: str, *, llm: Callable[[str], tuple[str, str]] = _call_llm) -> dict:
    view, audit = company_view(query), audit_checks(query)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{view['identity']['code']}|{day}"
    meta = {"identity": view["identity"], "disclaimer": DISCLAIMER_FA, "day": day,
            "dataLastUpdate": view["financials"]["lastUpdate"], "kiashaGeneratedAt": (view["kiasha"] or {}).get("generatedAt")}
    with _lock:
        conn = _ai_db()
        try:
            hit = conn.execute("SELECT body, model, created_at FROM report WHERE key=?", (key,)).fetchone()
            if hit:
                return {**meta, "report": hit[0], "model": hit[1], "generatedAt": hit[2], "cached": True}
            used = conn.execute("SELECT n FROM usage WHERE client=? AND day=?", (user_id, day)).fetchone()
            total = conn.execute("SELECT COALESCE(SUM(n),0) FROM usage WHERE day=?", (day,)).fetchone()[0]
            if total >= GLOBAL_DAILY_CAP:
                raise RateLimited("ظرفیت روزانه‌ی گزارش‌های هوش مصنوعی تمام شده است؛ گزارش‌های ذخیره‌شده در دسترس‌اند.")
            if used and used[0] >= USER_DAILY_LIMIT:
                raise RateLimited(f"سقف {USER_DAILY_LIMIT} گزارش جدید در روز پر شده است.")
            conn.execute("INSERT INTO usage(client, day, n) VALUES(?,?,1) ON CONFLICT(client, day) DO UPDATE SET n=n+1", (user_id, day))
            conn.commit()
        finally:
            conn.close()
    text, model = llm(_prompt(view, audit, day))
    created = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _ai_db()
        try:
            conn.execute("INSERT OR REPLACE INTO report(key, day, body, model, created_at) VALUES(?,?,?,?,?)", (key, day, text, model, created))
            conn.commit()
        finally:
            conn.close()
    return {**meta, "report": text, "model": model, "generatedAt": created, "cached": False}
