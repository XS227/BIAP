import json
import threading

import pytest

from global_markets.source_cache import read_json, write_json_atomic


def test_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "a" / "x.json"
    write_json_atomic(target, {"k": 1})
    assert read_json(target) == {"k": 1}
    assert [p.name for p in target.parent.iterdir()] == ["x.json"]


def test_failed_write_removes_temp_and_keeps_old_value(tmp_path):
    tmp_path = tmp_path / "d"
    tmp_path.mkdir()
    target = tmp_path / "x.json"
    write_json_atomic(target, {"ok": True})
    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": object()})
    assert read_json(target) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_concurrent_writers_never_corrupt(tmp_path):
    tmp_path = tmp_path / "d"
    tmp_path.mkdir()
    target = tmp_path / "x.json"
    errors = []

    def writer(n):
        try:
            for i in range(40):
                write_json_atomic(target, {"w": n, "pad": "x" * 5000, "i": i})
                json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]
