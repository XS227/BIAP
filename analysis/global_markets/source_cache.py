"""Small persistent cache for verified BIAP Global source indexes.

The cache is intentionally file-based so provider sync jobs can run separately
from the API process. Writes are atomic and stay outside the Git checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def data_root() -> Path:
    return Path(os.environ.get("BIAP_GLOBAL_DATA_DIR", "/var/lib/biap-global")).expanduser()


def source_index_path(name: str) -> Path:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        raise ValueError("invalid source index name")
    return data_root() / "source-index" / f"{safe}.json"


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def filing_path(country: str, source_id: str, suffix: str = ".bin") -> Path:
    country = country.strip().upper()
    safe_id = "".join(ch for ch in source_id if ch.isalnum() or ch in {"-", "_", "."})
    if not country or not safe_id:
        raise ValueError("invalid filing path")
    return data_root() / "filings" / country / f"{safe_id}{suffix}"
