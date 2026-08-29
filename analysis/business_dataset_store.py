"""Per-user persisted business datasets for BIAP mobile cross-device sync."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_STORE_PATH = Path(os.environ.get("BIAP_BUSINESS_DATASET_STORE", "/var/lib/biap/business_datasets.json"))


def _read_all() -> dict[str, dict[str, Any]]:
    if not _STORE_PATH.exists():
        return {}
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_all(data: dict[str, dict[str, Any]]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_STORE_PATH)


def get_dataset(user_id: str) -> dict[str, Any] | None:
    with _LOCK:
        item = _read_all().get(user_id)
        return item if isinstance(item, dict) else None


def save_dataset(user_id: str, dataset: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        data = _read_all()
        data[user_id] = dataset
        _write_all(data)
    return dataset


def delete_dataset(user_id: str) -> None:
    with _LOCK:
        data = _read_all()
        if user_id in data:
            del data[user_id]
            _write_all(data)
