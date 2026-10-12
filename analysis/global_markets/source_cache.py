"""Small persistent cache for verified BIAP Global source indexes.

The cache is intentionally file-based so provider sync jobs can run separately
from the API process. Writes are atomic and stay outside the Git checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


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


def write_bytes_atomic(path: Path, body: bytes) -> None:
    """Atomic binary write with a unique temp name, removed if the write fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.chmod(name, 0o664)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


# Regenerable raw-source caches are capped; the oldest entries are evicted first.
# Analysis ledgers, fundamentals, history and databases never live in these dirs.
CACHE_MIN_AGE_SECONDS = 3600
CACHE_ORPHAN_AGE_SECONDS = 2 * 3600
CACHE_CHECK_INTERVAL_SECONDS = 300
_last_budget_check: dict[str, float] = {}


def enforce_cache_budget(
    directory: Path,
    max_bytes: Optional[int] = None,
    *,
    env_var: str = "BIAP_CACHE_MAX_MB",
    default_mb: int = 4096,
    suffixes: tuple[str, ...] = (".json",),
    force: bool = False,
) -> int:
    """Evict the oldest cache files so ``directory`` stays under its byte budget.

    Throttled to one scan per directory per few minutes. Only regular,
    non-symlink files directly inside ``directory`` are considered; files
    younger than an hour are kept (they may be in use) and stale ``*.tmp``
    orphans from killed writers are removed. Returns the bytes freed.
    """
    key = str(directory)
    now = time.time()
    if not force and now - _last_budget_check.get(key, 0.0) < CACHE_CHECK_INTERVAL_SECONDS:
        return 0
    _last_budget_check[key] = now
    if max_bytes is None:
        try:
            max_bytes = int(float(os.environ.get(env_var, default_mb)) * 1024 * 1024)
        except ValueError:
            max_bytes = default_mb * 1024 * 1024
    entries: list[tuple[float, int, str]] = []
    total = freed = 0
    try:
        scan = list(os.scandir(directory))
    except OSError:
        return 0
    for entry in scan:
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if entry.name.endswith(".tmp"):
            if now - st.st_mtime > CACHE_ORPHAN_AGE_SECONDS:
                try:
                    os.unlink(entry.path)
                    freed += st.st_size
                except OSError:
                    pass
            continue
        if not entry.name.endswith(suffixes):
            continue
        total += st.st_size
        entries.append((st.st_mtime, st.st_size, entry.path))
    if total <= max_bytes:
        return freed
    for mtime, size, path in sorted(entries):
        if total <= max_bytes:
            break
        if now - mtime < CACHE_MIN_AGE_SECONDS:
            continue
        try:
            os.unlink(path)
        except OSError:
            continue
        total -= size
        freed += size
    return freed
