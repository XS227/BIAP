"""Kiasha recommendation for an InsCode the quote/CODAL lookups do not know: retry under the stored ticker instead of 404."""
import pytest
from fastapi import HTTPException

import api_server


def test_inscode_without_quote_or_codal_retries_under_the_stored_ticker(monkeypatch):
    seen = []

    def build(sym):
        seen.append(sym)
        return {"ticker": sym, "name_fa": sym} if sym == "وملت" else None
    monkeypatch.setattr(api_server, "find_quote", lambda code: None)
    monkeypatch.setattr(api_server, "build_company_from_symbol", build)
    monkeypatch.setattr(api_server, "_stored_ticker", lambda code: "وملت")
    company, source = api_server._company_or_404("10055255678920880")
    assert company["ticker"] == "وملت" and source == "codal" and seen == ["10055255678920880", "وملت"]


def test_still_404_when_no_ticker_is_known(monkeypatch):
    monkeypatch.setattr(api_server, "find_quote", lambda code: None)
    monkeypatch.setattr(api_server, "build_company_from_symbol", lambda sym: None)
    monkeypatch.setattr(api_server, "_stored_ticker", lambda code: None)
    with pytest.raises(HTTPException) as exc:
        api_server._company_or_404("99999999999")
    assert exc.value.status_code == 404
