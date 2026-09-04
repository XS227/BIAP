import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import listed_company_ingestion as ingestion
from listed_company_store import ListedCompanyStore


def _item(code: str, symbol: str, name: str, market: str = "TSE"):
    return SimpleNamespace(
        to_dict=lambda: {
            "code": code,
            "symbol": symbol,
            "name": name,
            "market": market,
            "source": "tsetmc",
        }
    )


def test_store_search_detail_and_status(tmp_path):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    assert store.upsert_universe([_item("1", "فولاد", "فولاد مبارکه اصفهان"), _item("2", "فملی", "ملی صنایع مس")]) == 2
    assert store.count() == 2
    assert [x["symbol"] for x in store.search("فولاد")] == ["فولاد"]
    assert [x["code"] for x in store.search(market="TSE")] == ["2", "1"] or len(store.search(market="TSE")) == 2

    company = {
        "ticker": "فولاد",
        "name_fa": "فولاد مبارکه اصفهان",
        "data_available": {"codal": True, "tindex": False},
        "market": {"price": 12345},
        "codal": {"net_margin_pct": 17.2},
    }
    store.save_enriched("1", company, provenance={"builder": "test"})
    detail = store.get("1")
    assert detail is not None
    assert detail["company"]["market"]["price"] == 12345
    assert detail["provenance"]["builder"] == "test"
    status = store.status()
    assert status["total"] == 2
    assert status["enriched"] == 1


def test_worker_resumes_from_saved_cursor(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([
        _item("1", "الف", "شرکت الف"),
        _item("2", "ب", "شرکت ب"),
        _item("3", "ج", "شرکت ج"),
    ])

    monkeypatch.setattr(ingestion, "refresh_universe", lambda target: {"ok": True, "count": target.count(), "source": "test"})
    built = []

    def fake_build(code):
        built.append(code)
        return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder")

    monkeypatch.setattr(ingestion, "_build_verified_company", fake_build)
    monkeypatch.delenv("TINDEX_API_TOKEN", raising=False)

    first = ingestion.run_batch(store=store, batch_size=1, reset=True)
    assert first["status"] == "paused"
    assert first["cursor"] == 1
    assert first["processed"] == 1
    assert first["metadata"]["externalBlockers"] == ["TINDEX_API_TOKEN missing in production environment"]

    second = ingestion.run_batch(store=store, batch_size=2)
    assert second["status"] == "completed"
    assert second["cursor"] == 3
    assert second["processed"] == 3
    assert second["succeeded"] == 3
    assert built == ["1", "2", "3"]
    assert store.status()["enriched"] == 3
