"""Opt-in AI explanation of an already stored Global company snapshot.

Only the narrow saved_company_view projection enters the prompt. The AI proxy
is never contacted by import or by a GET; only an explicit staging POST calls
it. No provider refresh, analysis worker, trade, or DB writer is used.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit


class ProxyUnavailable(RuntimeError):
    """Configured BIAP AI proxy is missing or returned an unusable response."""


def _proxy_base() -> str:
    base = os.environ.get("BIAP_AI_PROXY_URL", "").strip().rstrip("/")
    try:
        url = urlsplit(base)
        host = (url.hostname or "").lower()
        loopback = host in ("localhost", "127.0.0.1", "::1")
        valid = (url.scheme == "https" or (url.scheme == "http" and loopback))
        valid = valid and bool(host) and not url.username and not url.password
        valid = valid and not url.query and not url.fragment
        valid = valid and host not in ("api.anthropic.com", "api.openai.com")
    except ValueError:
        valid = False
    if not valid:
        raise ProxyUnavailable("An explicit BIAP AI proxy HTTPS/loopback URL is required.")
    return base


def prompt_from_saved(view: dict) -> str:
    if (view.get("mode") != "SAVED_READ_ONLY" or view.get("proxyCalled") is not False
            or view.get("eligibleForInvestmentDecision") is not False):
        raise ValueError("Refusing unverified or mutable company payload.")
    # Never forward raw ledger blobs, provider diagnostics, credentials or cache.
    safe = {k: view[k] for k in (
        "country", "exchange", "ticker", "name", "currency", "ledger",
        "financials", "financialQuality", "audit", "evidence", "agents", "kiasha"
    )}
    payload = json.dumps(safe, ensure_ascii=False, allow_nan=False)
    if len(payload) > 25000:
        raise ValueError("Stored company projection exceeds bounded AI prompt size.")
    return (
        "Explain this company's STORED BIAP snapshot in plain English. "
        "Use ONLY the JSON evidence; never invent figures, fresh prices, or sources. "
        "Do not recommend BUY/SELL, trading, or a price target. "
        "State missing data, report period, data-quality limitations, six agent "
        "observations (when present), Kiasha's stored conclusion, and deterministic "
        "audit flags. Clearly distinguish an AI explanation from a statutory audit. "
        "Use four short sections: Strengths, Weaknesses, Risks, Missing evidence.\n\n"
        "STORED_SNAPSHOT:\n" + payload
    )


def call_biap_proxy(prompt: str) -> tuple[str, str]:
    import httpx

    base = _proxy_base()
    model = os.environ.get("BIAP_CHECKPOINT_GLOBAL_AI_MODEL", "claude-sonnet-5")
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    token = os.environ.get("BIAP_AI_PROXY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = httpx.post(
            base + "/messages", headers=headers, timeout=45,
            json={"model": model, "max_tokens": 850, "messages": [{"role": "user", "content": prompt}]},
        )
    except httpx.HTTPError as exc:
        raise ProxyUnavailable("BIAP AI proxy request failed: " + type(exc).__name__) from exc
    if response.status_code != 200:
        raise ProxyUnavailable("BIAP AI proxy returned HTTP " + str(response.status_code))
    try:
        data = response.json()
        parts = data.get("content") if isinstance(data, dict) else None
        text = "".join(p.get("text", "") for p in (parts or []) if isinstance(p, dict)).strip()
    except (ValueError, TypeError):
        text = ""
    if not text or len(text) > 12000:
        raise ProxyUnavailable("BIAP AI proxy returned an empty or oversized explanation.")
    return text, model


def explain_saved_company(view: dict, *, call: Callable[[str], tuple[str, str]] = call_biap_proxy) -> dict:
    prompt = prompt_from_saved(view)
    report, model = call(prompt)
    if not isinstance(report, str) or not report.strip() or len(report) > 12000:
        raise ProxyUnavailable("BIAP AI proxy returned invalid text.")
    return {
        "mode": "SAVED_AI_EXPLANATION",
        "route": "biap-ai-proxy",
        "proxyCalled": True,
        "eligibleForInvestmentDecision": False,
        "country": view["country"], "exchange": view["exchange"], "ticker": view["ticker"],
        "dataAnalyzedAt": view["ledger"].get("analyzedAt"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "report": report,
        "disclaimer": "AI explanation of stored evidence, not an audit or investment recommendation.",
    }
