from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import listed_company_ingestion as ingestion
from codal_data import CodalDataUnavailable
from listed_company_store import ListedCompanyStore


def _item(code: str, symbol: str, *, market=None, source="tsetmc"):
    data = {
        "code": code,
        "symbol": symbol,
        "name": symbol,
        "market": market,
        "source": source,
    }
    return SimpleNamespace(
        code=code,
        symbol=symbol,
        name=symbol,
        market=market,
        source=source,
        to_dict=lambda: dict(data),
    )


def test_refresh_universe_uses_codal_issuer_whitelist(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    companies = [_item(str(i), f"CO{i}", market=None) for i in range(100)]
    derivatives = [_item(f"D{i}", f"OPT{i}", market=None) for i in range(20)]

    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: companies + derivatives)
    monkeypatch.setattr(ingestion, "list_companies", lambda: [{"sy": f"CO{i}"} for i in range(100)])

    result = ingestion.refresh_universe(store)

    assert result["strategy"] == "tsetmc-codal-issuer-whitelist"
    assert result["rawUniverseCount"] == 120
    assert result["selectedThisRefresh"] == 100
    assert result["filteredOutThisRefresh"] == 20
    assert result["count"] == 100
    assert all(not code.startswith("D") for code in result["_codes"])
    assert store.get("0")["sourceUniverse"] == "listed-company-tsetmc-codal"


def test_refresh_universe_falls_back_to_market_classification(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    market_company = _item("1", "COMPANY", market="TSE")
    unknown_instrument = _item("2", "OPTION", market=None)

    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: [market_company, unknown_instrument])

    def unavailable():
        raise CodalDataUnavailable("blocked")

    monkeypatch.setattr(ingestion, "list_companies", unavailable)

    result = ingestion.refresh_universe(store)

    assert result["strategy"] == "tsetmc-market-fallback"
    assert result["count"] == 1
    assert result["_codes"] == ["1"]
    assert store.get("1")["sourceUniverse"] == "listed-company-tsetmc-market"
    assert store.get("2") is None
