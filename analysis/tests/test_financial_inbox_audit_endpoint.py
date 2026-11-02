"""Checkpoint 1: authenticated Liara-only audit endpoint must fail closed."""
from pathlib import Path
import sys
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import api_server
from codal_inbox import InboxError


class StubInbox:
    def summary(self):
        return {"exports": 1, "newestExport": "2026-11-02", "rejected": []}

    def record(self, symbol):
        if symbol != "پکرمان":
            raise InboxError("CODAL_INBOX_MISS")
        return {"status": "ok", "company": {"n": "گروه صنعتی بارز"},
                "financial_filings": [{"tracing_no": "42",
                    "title": "صورت‌های مالی (شرکت لاستیک بارز کردستان)"}]}

    def report_html(self, tracing_no):
        return "<table><tr><td>unvalidated</td></tr></table>"


def test_endpoint_is_authenticated():
    route = next(r for r in api_server.app.routes if getattr(r, "path", "") == "/audit/financial-inbox/{symbol}")
    assert route.methods == {"GET"}
    assert any(d.call is api_server.require_user_id for d in route.dependant.dependencies)


def test_endpoint_is_read_only_and_fail_closed(monkeypatch):
    monkeypatch.setattr(api_server, "current_codal_inbox", StubInbox)
    result = api_server.financial_inbox_audit("پکرمان", "test-user")
    assert result["source"] == "verified_liara_codal_inbox_only"
    assert result["company"]["explicit_issuer_review"] == 1
    assert result["company"]["financial_ai_eligible"] is False
    assert result["company"]["market_price_reconciliation"] == "NOT_POSSIBLE_FROM_CODAL_INBOX_ALONE"
    assert result["company"]["filing_evidence"][0]["quality_gate"].startswith("BLOCKED")
    assert "html" not in result["company"]["filing_evidence"][0]


def test_missing_symbol_never_falls_back_to_network(monkeypatch):
    monkeypatch.setattr(api_server, "current_codal_inbox", StubInbox)
    with pytest.raises(HTTPException) as exc:
        api_server.financial_inbox_audit("نامعلوم", "test-user")
    assert exc.value.status_code == 404


def test_missing_inbox_is_503(monkeypatch):
    def missing():
        raise InboxError("BIAP_CODAL_INBOX is not set")
    monkeypatch.setattr(api_server, "current_codal_inbox", missing)
    with pytest.raises(HTTPException) as exc:
        api_server.financial_inbox_audit("پکرمان", "test-user")
    assert exc.value.status_code == 503


def test_no_verified_exports_is_503(monkeypatch):
    class EmptyInbox(StubInbox):
        def summary(self):
            return {"exports": 0, "rejected": [{"date": "2026-11-02"}]}
    monkeypatch.setattr(api_server, "current_codal_inbox", EmptyInbox)
    with pytest.raises(HTTPException) as exc:
        api_server.financial_inbox_audit("پکرمان", "test-user")
    assert exc.value.status_code == 503


def test_unreadable_inbox_is_503_not_false_symbol_miss(monkeypatch):
    class UnreadableInbox(StubInbox):
        def record(self, symbol):
            raise InboxError("verified Liara report index unreadable")
    monkeypatch.setattr(api_server, "current_codal_inbox", UnreadableInbox)
    with pytest.raises(HTTPException) as exc:
        api_server.financial_inbox_audit("پکرمان", "test-user")
    assert exc.value.status_code == 503
