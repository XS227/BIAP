"""BIAP_GLOBAL_ONLINE_FIRST: raw-source caches must not persist to disk."""
from global_markets import source_cache as sc


def test_bulk_json_not_persisted_when_online_first(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_ONLINE_FIRST", "1")
    target = tmp_path / "cache" / "x.json"
    sc.write_bulk_json(target, {"a": 1})
    assert not target.exists() and not target.parent.exists()
    assert sc.read_json(target) == {"a": 1}  # served from bounded memo


def test_bulk_json_persisted_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_ONLINE_FIRST", raising=False)
    target = tmp_path / "cache" / "y.json"
    sc.write_bulk_json(target, {"b": 2})
    assert sc.read_json(target) == {"b": 2} and target.exists()


def test_memo_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_ONLINE_FIRST", "1")
    root = tmp_path / "bulk"
    for i in range(sc._MEMO_MAX_ENTRIES + 20):
        sc.write_bulk_json(root / f"{i}.json", {"i": i})
    assert len(sc._memo) <= sc._MEMO_MAX_ENTRIES
    assert not root.exists()


def test_bulk_text_not_persisted_when_online_first(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_ONLINE_FIRST", "1")
    target = tmp_path / "universe" / "z.json"
    sc.write_bulk_text(target, "{}")
    assert not target.parent.exists()
    monkeypatch.delenv("BIAP_GLOBAL_ONLINE_FIRST")
    sc.write_bulk_text(target, "{}")
    assert target.read_text() == "{}"


def test_issuer_drop_sync_skips_when_online_first(monkeypatch, capsys):
    from global_markets import issuer_drop_sync
    monkeypatch.setenv("BIAP_GLOBAL_ONLINE_FIRST", "1")
    assert issuer_drop_sync.main() == 0
    assert "skipped" in capsys.readouterr().out
