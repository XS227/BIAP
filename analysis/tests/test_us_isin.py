from global_markets import us_isin
from global_markets.us_isin import enrich_with_us_isin, is_valid_isin, issuer_tokens, resolve_us_isin
from tests.test_global_governance_agent import _company

AAPL_LEI = "HWUPKR0MPOU8FGXBT394"


class FakeHttp:
    def __init__(self, *, figi_ticker="AAPL", figi_name="APPLE INC", raise_on=None):
        self.calls = []
        self.figi_ticker, self.figi_name, self.raise_on = figi_ticker, figi_name, raise_on

    def get(self, url, params=None):
        self.calls.append(("get", url))
        if self.raise_on == "gleif":
            raise RuntimeError("down")
        if url.endswith("/lei-records"):
            return {"data": [{"id": AAPL_LEI, "attributes": {"entity": {"legalName": {"name": "Apple Inc."}}}}]}
        return {
            "meta": {"pagination": {"lastPage": 1}},
            "data": [{"attributes": {"isin": i}} for i in ("US037833EK20", "US0378331005", "US037833AK68")],
        }

    def post(self, url, payload):
        self.calls.append(("post", url))
        out = []
        for job in payload:
            ok = job["idValue"] == "US0378331005"
            out.append({"data": [{"figi": "BBG000B9XRY4", "name": self.figi_name, "ticker": self.figi_ticker,
                                  "marketSector": "Equity", "securityType": "Common Stock"}]} if ok else {"error": "No identifier found."})
        return out


def test_isin_check_digit_validation():
    assert is_valid_isin("US0378331005") and is_valid_isin("US02079K3059") and is_valid_isin("USN070592100")
    assert not is_valid_isin("US0378331006") and not is_valid_isin("garbage")


def test_resolves_only_the_equity_isin_with_matching_ticker_and_name():
    found = resolve_us_isin("AAPL", "Apple Inc. - Common Stock", http=FakeHttp())
    assert found["isin"] == "US0378331005" and found["lei"] == AAPL_LEI and found["provenance"] == us_isin.PROVENANCE


def test_ticker_mismatch_or_name_mismatch_stays_unresolved():
    assert resolve_us_isin("AAPL", "Apple Inc.", http=FakeHttp(figi_ticker="MSFT")) is None
    assert resolve_us_isin("AAPL", "Apple Inc.", http=FakeHttp(figi_name="MICROSOFT CORP")) is None


def test_provider_failure_returns_none_not_an_exception():
    assert resolve_us_isin("AAPL", "Apple Inc.", http=FakeHttp(raise_on="gleif")) is None


def test_restricted_cusip_datasets_are_not_used():
    src = open(us_isin.__file__).read().lower()
    assert "13flist" not in src and "sec.gov/files" not in src and "isin_from_cusip" not in src


def test_enrichment_is_flag_gated_and_never_changes_analytics(monkeypatch):
    company = _company()
    monkeypatch.delenv("BIAP_GLOBAL_US_ISIN_RESOLVE", raising=False)
    assert enrich_with_us_isin(company) is company
    monkeypatch.setenv("BIAP_GLOBAL_US_ISIN_RESOLVE", "1")
    monkeypatch.setattr(us_isin, "resolve_us_isin", lambda *a, **k: None)
    us_isin._cached.cache_clear()
    assert enrich_with_us_isin(company).isin is None  # unresolved -> unchanged
    monkeypatch.setattr(us_isin, "resolve_us_isin", lambda *a, **k: {"isin": "US0378331005", "lei": AAPL_LEI, "figi": "F"})
    us_isin._cached.cache_clear()
    out = enrich_with_us_isin(company)
    assert out.isin == "US0378331005" and out.pe == company.pe and out.price == company.price
    assert out.raw_provider_fields["isin_resolution"]["provenance"] == us_isin.PROVENANCE


def test_tokens():
    assert issuer_tokens("Walt Disney Company (The) Common Stock") == ["WALT", "DISNEY"]
