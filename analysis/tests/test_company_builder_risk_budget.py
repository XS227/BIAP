"""A slow CODAL PDF relay must not discard a statement we already hold (nightly 'no verified company data' root cause)."""
import time
from dataclasses import dataclass

import company_builder as cb


@dataclass(frozen=True)
class _F:
    revenue: float = 1.0
    audit_opinion: str | None = None
    related_party_flags: str | None = None

    def to_dict(self):
        return {"revenue": self.revenue, "audit_opinion": self.audit_opinion}


def _patch(monkeypatch, enrich):
    cb._codal_parts_cache.clear()
    monkeypatch.setattr(cb, "metadata_for_symbol", lambda s: None)
    monkeypatch.setattr(cb, "scoped_fundamentals_for_symbol", lambda s: (_F(), "consolidated"))
    monkeypatch.setattr(cb, "_enrich_codal_risk_fields", enrich)
    monkeypatch.setenv("BIAP_CODAL_RISK_BUDGET_SECONDS", "0.6")


def test_slow_pdf_lookup_keeps_the_statement_and_marks_risk_fields_deferred(monkeypatch):
    _patch(monkeypatch, lambda sym, f, scope: (time.sleep(3), f)[1])
    t = time.monotonic()
    meta, fund, diag = cb._codal_parts("سیدکو")
    assert time.monotonic() - t < 2.0
    assert fund is not None and fund["revenue"] == 1.0 and fund["report_scope"] == "consolidated"
    assert diag["status"] == "ok" and diag["riskFields"] == "deferred"


def test_fast_lookup_still_enriches(monkeypatch):
    _patch(monkeypatch, lambda sym, f, scope: _F(audit_opinion="unqualified"))
    _, fund, diag = cb._codal_parts("سیدکو")
    assert fund["audit_opinion"] == "unqualified" and "riskFields" not in diag


def test_failing_lookup_keeps_the_statement(monkeypatch):
    def boom(sym, f, scope):
        raise RuntimeError("relay down")
    _patch(monkeypatch, boom)
    _, fund, diag = cb._codal_parts("سیدکو")
    assert fund is not None and diag["riskFields"] == "unavailable"
