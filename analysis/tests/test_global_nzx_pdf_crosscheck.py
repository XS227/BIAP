import pytest

from global_markets import nzx_issuer as n
from global_markets.pdf_statements import PDFExtractionError
from global_markets.providers import GlobalProviderError


class _R:
    currency = "NZD"
    audit_opinion = "unqualified"
    audit_pages = [9]
    statement_pages = {"balance": [5]}
    checks = {}

    def __init__(self, revenue):
        self._rev = revenue

    def values(self):
        return {"revenue": self._rev}

    def provenance(self):
        return {"revenue": {"page": 4, "label": "Operating revenue", "raw": "100", "scale": 1.0, "scope": "consolidated"}}


def _patch(monkeypatch, result=None, error=None):
    def fake(*a, **k):
        if error:
            raise error
        return result
    monkeypatch.setattr(n, "read_pdf_pages", lambda c: {1: ""})
    monkeypatch.setattr(n, "extract_primary_statements", fake)


def _run(metrics):
    return n.pdf_provenance_crosscheck(b"x", ticker="SUM", period_end="2025-12-31", metrics=metrics, report_url="https://api.nzx.com/a.pdf")


def test_verified_carries_url_page_period_currency(monkeypatch):
    _patch(monkeypatch, _R(100.0))
    out = _run({"revenue": 100.0})
    f = out["fields"]["revenue"]
    assert out["status"] == "verified"
    assert (f["document_url"], f["page"], f["fiscal_period_end"], f["currency"], f["label"]) == (
        "https://api.nzx.com/a.pdf", 4, "2025-12-31", "NZD", "Operating revenue")


def test_disagreement_blocks(monkeypatch):
    _patch(monkeypatch, _R(100.0))
    with pytest.raises(GlobalProviderError):
        _run({"revenue": 120.0})


def test_extractor_rejection_is_unverified_not_provenance(monkeypatch):
    _patch(monkeypatch, error=PDFExtractionError("no balance sheet"))
    out = _run({"revenue": 100.0})
    assert out["status"] == "unverified" and "fields" not in out


def test_pdf_evidence_blocks_on_rejection(monkeypatch):
    _patch(monkeypatch, error=PDFExtractionError("ambiguous"))
    with pytest.raises(GlobalProviderError):
        n.pdf_evidence(b"x", legal_name="X", period_end="2025-12-31", currency="NZD", report_url="u")
