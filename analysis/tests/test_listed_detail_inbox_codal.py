import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import codal_inbox
import company_builder
import listed_company_routes as routes


def test_stored_codal_is_never_replaced(monkeypatch):
    monkeypatch.setattr(codal_inbox, "enabled", lambda: True)
    monkeypatch.setattr(company_builder, "_codal_parts", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert routes._inbox_codal({"symbol": "X"}, {"codal": {"total_assets_current": 1}}) == (None, None)


def test_missing_stored_codal_uses_inbox_scoped_parser(monkeypatch):
    monkeypatch.setattr(codal_inbox, "enabled", lambda: True)
    monkeypatch.setattr(company_builder, "_codal_parts", lambda symbol, lightweight=False: ({"title": "m"}, {"total_assets_current": 340995803.0}, {}))
    meta, fund = routes._inbox_codal({"symbol": "پکرمان"}, {"codal": None})
    assert fund == {"total_assets_current": 340995803.0} and meta == {"title": "m"}


def test_inbox_disabled_means_no_lookup_and_no_direct_codal_call(monkeypatch):
    monkeypatch.setattr(codal_inbox, "enabled", lambda: False)
    monkeypatch.setattr(company_builder, "_codal_parts", lambda *a, **k: (_ for _ in ()).throw(AssertionError("direct CODAL call")))
    assert routes._inbox_codal({"symbol": "تابان"}, {}) == (None, None)


def test_lookup_failure_is_soft(monkeypatch):
    monkeypatch.setattr(codal_inbox, "enabled", lambda: True)
    def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(company_builder, "_codal_parts", boom)
    assert routes._inbox_codal({"symbol": "تابان"}, {}) == (None, None)
