import listed_company_ingestion as lci


class _Reg:
    def get_instrument(self, code):
        return {"symbol": "شپنا"} if code == "7745894403636165" else None


def test_numeric_code_falls_back_to_registry_symbol(monkeypatch):
    seen = []
    monkeypatch.setattr(lci, "find_quote", lambda code: (_ for _ in ()).throw(lci.MarketDataUnavailable("x")))
    monkeypatch.setattr(lci, "CompanyRegistryStore", lambda *a, **k: _Reg())
    monkeypatch.setattr(lci, "build_company_from_symbol", lambda s: seen.append(s) or {"ticker": s})
    company, _ = lci._build_verified_company("7745894403636165")
    assert seen == ["شپنا"] and company["ticker"] == "شپنا"


def test_symbol_code_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(lci, "find_quote", lambda code: (_ for _ in ()).throw(lci.MarketDataUnavailable("x")))
    monkeypatch.setattr(lci, "build_company_from_symbol", lambda s: seen.append(s) or {})
    lci._build_verified_company("یکتانت")
    assert seen == ["یکتانت"]
