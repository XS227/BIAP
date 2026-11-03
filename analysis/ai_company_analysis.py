"""AI company analysis from STORED BIAP data only (additive; read-only on analysis stores).

Contract
- Facts come from already-stored analyses (agent votes, Kiasha/Global result, statements, ratios,
  distress). Nothing is fetched from the web and the model is told to use nothing else.
- The LLM key lives only in the server environment (EnvironmentFile, mode 600). It is never
  returned, logged or sent to an app.  Base URL is configurable: BIAP_AI_BASE_URL.
- One report per (kind, symbol, UTC day) is cached; a cache hit costs no quota.
- Per-user daily quota (BIAP_AI_DAILY_LIMIT, default 10 fresh reports / user / day).
- A tiny probe request runs first (cached 5 min); auth/credit failure => AI_UNAVAILABLE and the
  report is never invented.  Missing facts => INSUFFICIENT_DATA without calling the model.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

DEFAULT_DB = "/var/lib/biap/ai-company-analysis.sqlite3"
LABEL = {
    "en": "AI-generated, not investment advice",
    "fa": "تولیدشده با هوش مصنوعی؛ توصیه‌ی سرمایه‌گذاری نیست",
}
SYSTEM_PROMPT = (
    "You write a short company analysis for a retail app. Use ONLY the JSON facts supplied; do not use "
    "outside knowledge, do not invent numbers, dates, ratings or prices, and do not give buy/sell/hold advice "
    "or price targets. Where a fact is null or absent, list it under missingData. Reply with ONE JSON object: "
    '{"summary": str, "strengths": [str], "weaknesses": [str], "risks": [str], "missingData": [str]}. '
    "Each item is one sentence that cites the agent or field it comes from. Write in the requested language."
)
_probe_lock = threading.Lock()
_probe_state: dict[str, Any] = {"at": 0.0, "ok": False, "reason": None}


def db_path() -> str:
    return os.getenv("BIAP_AI_CACHE_DB", DEFAULT_DB)


def _connect(path: Optional[str] = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS ai_reports (kind TEXT, symbol TEXT, day TEXT, lang TEXT, facts_hash TEXT, created_at TEXT, model TEXT, report_json TEXT, PRIMARY KEY(kind,symbol,day,lang))")
    con.execute("CREATE TABLE IF NOT EXISTS ai_usage (user_key TEXT, day TEXT, n INTEGER, PRIMARY KEY(user_key,day))")
    return con


def daily_limit() -> int:
    try:
        return max(1, int(os.getenv("BIAP_AI_DAILY_LIMIT", "10")))
    except ValueError:
        return 10


def base_url() -> str:
    return os.getenv("BIAP_AI_BASE_URL", os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com/v1")).rstrip("/")


def _api_key() -> str:
    return (os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")).strip()


def facts_sufficient(facts: dict) -> bool:
    agents = facts.get("agents") or []
    return any(a.get("vote") is not None for a in agents if isinstance(a, dict))


def _classify_http(status: int, body: str) -> str:
    low = body.lower()
    if status in (401, 403) or "authentication" in low:
        return "auth"
    if status == 402 or "credit" in low or "billing" in low:
        return "credit"
    if status == 429:
        return "rate"
    return "http_%d" % status


def http_llm(system: str, user: str, *, max_tokens: int, timeout: float = 45.0) -> str:
    """POST to the configured Messages-compatible endpoint; returns text. Raises LLMError(reason)."""
    import httpx

    key = _api_key()
    if not key:
        raise LLMError("no_key")
    model = os.getenv("BIAP_AI_MODEL", os.getenv("KIASHA_AI_MODEL", "claude-sonnet-5-5"))
    try:
        r = httpx.post(
            f"{base_url()}/messages", timeout=timeout,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]},
        )
    except httpx.HTTPError as exc:
        raise LLMError("network:" + type(exc).__name__) from exc
    if r.status_code >= 400:
        raise LLMError(_classify_http(r.status_code, r.text[:300]))
    parts = [b.get("text", "") for b in (r.json().get("content") or []) if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(parts)


class LLMError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def probe(llm: Callable[..., str] = http_llm, *, now: Optional[float] = None, ttl: float = 300.0) -> tuple[bool, Optional[str]]:
    """Tiny request to confirm the key works and credit is not exhausted (cached ttl seconds)."""
    t = time.time() if now is None else now
    with _probe_lock:
        if t - _probe_state["at"] < ttl:
            return _probe_state["ok"], _probe_state["reason"]
        try:
            llm("Reply with: ok", "ok", max_tokens=4, timeout=15.0)
            _probe_state.update(at=t, ok=True, reason=None)
        except LLMError as exc:
            _probe_state.update(at=t, ok=False, reason=exc.reason)
        return _probe_state["ok"], _probe_state["reason"]


def reset_probe() -> None:
    _probe_state.update(at=0.0, ok=False, reason=None)


def _parse_report(text: str) -> Optional[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), str):
        return None

    def items(key: str) -> list[str]:
        v = raw.get(key)
        return [str(x)[:400] for x in v][:8] if isinstance(v, list) else []

    return {"summary": raw["summary"][:800], "strengths": items("strengths"), "weaknesses": items("weaknesses"),
            "risks": items("risks"), "missingData": items("missingData")}


def run(kind: str, symbol: str, facts: dict, user_key: str, lang: str = "en", *,
        db: Optional[str] = None, llm: Callable[..., str] = http_llm, now: Optional[datetime] = None) -> dict:
    lang = "fa" if lang == "fa" else "en"
    moment = now or datetime.now(timezone.utc)
    day = moment.date().isoformat()
    base = {"kind": kind, "symbol": symbol, "date": day, "language": lang, "label": LABEL[lang], "report": None}
    if not facts_sufficient(facts):
        return {**base, "status": "INSUFFICIENT_DATA", "cached": False,
                "reason": "No stored agent result with a vote is available for this company."}
    facts_hash = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]
    con = _connect(db)
    try:
        row = con.execute("SELECT * FROM ai_reports WHERE kind=? AND symbol=? AND day=? AND lang=?", (kind, symbol, day, lang)).fetchone()
        if row:
            return {**base, "status": "OK", "cached": True, "generatedAt": row["created_at"], "model": row["model"],
                    "report": json.loads(row["report_json"]), "factsHash": row["facts_hash"]}
        used = con.execute("SELECT n FROM ai_usage WHERE user_key=? AND day=?", (user_key, day)).fetchone()
        if used and used["n"] >= daily_limit():
            return {**base, "status": "RATE_LIMITED", "cached": False, "limit": daily_limit(),
                    "reason": "Daily AI analysis limit reached for this user."}
        ok, why = probe(llm)
        if not ok:
            return {**base, "status": "AI_UNAVAILABLE", "cached": False, "reason": "AI service unavailable (%s)." % why}
        prompt = "Language: %s\nFACTS (the only allowed source):\n%s" % ("Persian" if lang == "fa" else "English", json.dumps(facts, ensure_ascii=False, default=str))
        try:
            text = llm(SYSTEM_PROMPT, prompt, max_tokens=900)
        except LLMError as exc:
            return {**base, "status": "AI_UNAVAILABLE", "cached": False, "reason": "AI service unavailable (%s)." % exc.reason}
        report = _parse_report(text)
        if report is None:
            return {**base, "status": "AI_UNAVAILABLE", "cached": False, "reason": "AI reply was not a valid report."}
        model = os.getenv("BIAP_AI_MODEL", os.getenv("KIASHA_AI_MODEL", ""))
        created = moment.isoformat()
        con.execute("INSERT OR REPLACE INTO ai_reports VALUES (?,?,?,?,?,?,?,?)", (kind, symbol, day, lang, facts_hash, created, model, json.dumps(report, ensure_ascii=False)))
        con.execute("INSERT INTO ai_usage VALUES (?,?,1) ON CONFLICT(user_key,day) DO UPDATE SET n=n+1", (user_key, day))
        con.commit()
        return {**base, "status": "OK", "cached": False, "generatedAt": created, "model": model, "report": report, "factsHash": facts_hash}
    finally:
        con.close()


# ---- facts builders (stored data only) --------------------------------------------------------

def _trim(text: Any, n: int = 300) -> Any:
    return text[:n] if isinstance(text, str) else text


def iran_facts(rec: dict) -> dict:
    return {
        "market": "Iran (TSE/IFB)",
        "finalCall": rec.get("call"), "finalScore": rec.get("score"), "analysedAt": rec.get("generatedAt"),
        "dataSource": rec.get("dataSource"), "dataAvailability": rec.get("dataAvailability"),
        "agents": [{"agent": b.get("agent"), "vote": b.get("vote"), "confidence": b.get("confidence"),
                    "observedSamples": b.get("observed_samples"), "weight": b.get("weight_normalized"),
                    "reasoning": _trim(b.get("reasoning"))} for b in (rec.get("breakdown") or []) if isinstance(b, dict)],
        "statements": rec.get("codalFundamentals"),
    }


def global_facts(res: dict) -> dict:
    fe = res.get("fundamentalEvidence") or {}
    return {
        "market": "%s/%s" % (res.get("country"), res.get("exchange")), "name": res.get("name"), "isin": res.get("isin"),
        "finalCall": res.get("call"), "confidence": res.get("confidence"), "analysedAt": res.get("analyzedAt"),
        "agents": [{"agent": s.get("agent"), "vote": s.get("vote"), "confidence": s.get("confidence"),
                    "reasoning": _trim(s.get("reasoning") or s.get("summary"))} for s in (res.get("signals") or []) if isinstance(s, dict)],
        "statements": fe.get("values"), "statementPeriod": fe.get("period"), "distress": res.get("distress"),
        "auditOpinion": (res.get("company") or {}).get("audit_opinion"),
    }
