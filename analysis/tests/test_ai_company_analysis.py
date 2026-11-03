import json
from datetime import datetime, timezone

import ai_company_analysis as aca

GOOD = {"agents": [{"agent": "fundamental", "vote": 0.2, "confidence": 0.65}], "statements": {"revenue": 1}}
REPLY = json.dumps({"summary": "s", "strengths": ["a"], "weaknesses": ["b"], "risks": ["c"], "missingData": ["d"]})
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def fake(calls):
    def llm(system, user, *, max_tokens, timeout=0):
        calls.append(max_tokens)
        return "ok" if max_tokens <= 4 else REPLY
    return llm


def test_insufficient_data_never_calls_model(tmp_path):
    calls = []
    out = aca.run("iran", "X", {"agents": [{"agent": "a", "vote": None}]}, "u", "en", db=str(tmp_path / "d"), llm=fake(calls), now=NOW)
    assert out["status"] == "INSUFFICIENT_DATA" and out["report"] is None and calls == []


def test_ok_cached_and_labelled(tmp_path):
    aca.reset_probe(); calls = []; db = str(tmp_path / "d")
    a = aca.run("iran", "X", GOOD, "u", "fa", db=db, llm=fake(calls), now=NOW)
    b = aca.run("iran", "X", GOOD, "other", "fa", db=db, llm=fake(calls), now=NOW)
    assert a["status"] == "OK" and not a["cached"] and b["cached"] and b["report"] == a["report"]
    assert "توصیه" in a["label"] and calls.count(900) == 1


def test_rate_limit_per_user(tmp_path, monkeypatch):
    aca.reset_probe(); monkeypatch.setenv("BIAP_AI_DAILY_LIMIT", "1"); calls = []; db = str(tmp_path / "d")
    assert aca.run("iran", "A", GOOD, "u", "en", db=db, llm=fake(calls), now=NOW)["status"] == "OK"
    assert aca.run("iran", "B", GOOD, "u", "en", db=db, llm=fake(calls), now=NOW)["status"] == "RATE_LIMITED"
    assert aca.run("iran", "B", GOOD, "v", "en", db=db, llm=fake(calls), now=NOW)["status"] == "OK"


def test_bad_key_or_credit_gives_unavailable_not_fake_report(tmp_path):
    aca.reset_probe()

    def dead(system, user, *, max_tokens, timeout=0):
        raise aca.LLMError("auth")
    out = aca.run("iran", "X", GOOD, "u", "en", db=str(tmp_path / "d"), llm=dead, now=NOW)
    assert out["status"] == "AI_UNAVAILABLE" and out["report"] is None and "auth" in out["reason"]
    aca.reset_probe()


def test_classify():
    assert aca._classify_http(401, "x") == "auth" and aca._classify_http(400, "credit balance is too low") == "credit"
