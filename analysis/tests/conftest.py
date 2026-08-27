import pytest

import kiasha
from performance_store import PerformanceStore


@pytest.fixture(autouse=True)
def _isolated_performance_store(tmp_path, monkeypatch):
    """Prevent any test from writing into the real production performance DB.

    kiasha.decide() records every call into performance_store.py's default
    (production) SQLite file unless kiasha._performance_store is overridden.
    Tests that exercise decide()/the recommendation pipeline without
    overriding it (e.g. via api_server's TestClient) would otherwise leave
    fixture rows like TSE1/IFB1/BASE1/SAMPLE1 in biap_performance.sqlite3.
    Tests that need their own store still override this via monkeypatch.
    """
    store = PerformanceStore(str(tmp_path / "test_performance.sqlite3"))
    monkeypatch.setattr(kiasha, "_performance_store", lambda: store)
    yield store
