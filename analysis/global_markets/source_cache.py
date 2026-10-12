"""Small persistent cache for verified BIAP Global source indexes.

The cache is intentionally file-based so provider sync jobs can run separately
from the API process. Writes are atomic and stay outside the Git checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
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
    # A unique temp name per write: concurrent workers share cache keys, and a
    # fixed "<name>.tmp" let two writers clobber each other. The temp file is
    # removed if the write fails, so no zero-byte orphans accumulate.
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        os.chmod(name, 0o664)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def filing_path(country: str, source_id: str, suffix: str = ".bin") -> Path:
    country = country.strip().upper()
    safe_id = "".join(ch for ch in source_id if ch.isalnum() or ch in {"-", "_", "."})
    if not country or not safe_id:
        raise ValueError("invalid filing path")
    return data_root() / "filings" / country / f"{safe_id}{suffix}"
