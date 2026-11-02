"""Consistent online backup of the accounting DB (SQLite backup API), with rotation.

Run from cron/systemd (owner installs the timer; nothing is installed from here):
    python -m accounting.store.backup /path/accounting.db /path/backups --keep 14
Backups are chmod 0600, integrity-checked, and the program prints only file names.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def backup(db_path: str | os.PathLike, dest_dir: str | os.PathLike, keep: int = 14) -> Path:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = dest / f"accounting-{stamp}.db"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = sqlite3.connect(target)
    try:
        src.backup(out)
        ok = out.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        out.close()
        src.close()
    if ok != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError("backup failed integrity check")
    os.chmod(target, 0o600)
    for old in sorted(dest.glob("accounting-*.db"))[:-keep] if keep > 0 else []:
        old.unlink()
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("dest")
    ap.add_argument("--keep", type=int, default=14)
    a = ap.parse_args()
    print(backup(a.db, a.dest, a.keep).name)


if __name__ == "__main__":
    main()
