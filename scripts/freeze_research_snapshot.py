#!/usr/bin/env python3
"""Freeze the research-paper snapshot: read-only, WAL-consolidated copies of the in-scope ledgers + sha256 manifest.

Only the exchanges in ``INVESTMENT_MODE_MARKETS`` are copied. Source ledgers are never opened: each is copied
(db + -wal + -shm) into ``--tmp-dir`` first, the COPY is checkpointed into one plain sqlite file, and that file is
placed in the snapshot with mode 0444. All paper analyses must read ONLY from the snapshot.

    python3 scripts/freeze_research_snapshot.py --snapshot ~/biap_research/snapshot_2026-10-19 --tmp-dir ~/biap_research/tmp/freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from global_markets import investment_mode as im  # noqa: E402

LEDGER_DIR = Path("/var/lib/biap-global/analysis-ledger")
SECTOR_REF = Path("/var/lib/biap-global/sector-reference/entries.json")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def consolidated_copy(src: Path, tmp: Path, dst: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    work = tmp / src.name
    shutil.copy2(src, work)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy2(side, tmp / side.name)
    conn = sqlite3.connect(work)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit(f"integrity_check failed for the copy of {src.name}")
    finally:
        conn.close()
    shutil.move(str(work), dst)
    for side in tmp.glob(src.name + "-*"):
        side.unlink()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--tmp-dir", required=True)
    ap.add_argument("--ledger-dir", default=str(LEDGER_DIR))
    args = ap.parse_args(argv)
    snap, tmp, ledgers = Path(args.snapshot).expanduser(), Path(args.tmp_dir).expanduser(), Path(args.ledger_dir)
    (snap / "ledgers").mkdir(parents=True, exist_ok=True)
    (snap / "reference").mkdir(parents=True, exist_ok=True)
    manifest = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scope": list(im.INVESTMENT_MODE_MARKETS),
                "note": "read-only copies; ledgers WAL-consolidated (journal_mode=DELETE); source sha256 = the live main file at copy time",
                "files": {}}
    for ex in im.INVESTMENT_MODE_MARKETS:
        cc, name = ex.split(":", 1)
        src = ledgers / f"{cc}__{name}.sqlite3"
        dst = snap / "ledgers" / src.name
        if dst.exists():
            raise SystemExit(f"{dst} already exists - a frozen snapshot is never overwritten")
        consolidated_copy(src, tmp, dst)
        os.chmod(dst, 0o444)
        manifest["files"][f"ledgers/{src.name}"] = {"sha256": sha256(dst), "bytes": dst.stat().st_size,
                                                    "source": str(src), "source_main_sha256": sha256(src),
                                                    "source_mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(src.stat().st_mtime))}
    ref = snap / "reference" / "sector_reference_entries.json"
    shutil.copy2(SECTOR_REF, ref)
    os.chmod(ref, 0o444)
    manifest["files"]["reference/sector_reference_entries.json"] = {"sha256": sha256(ref), "bytes": ref.stat().st_size, "source": str(SECTOR_REF)}
    man = snap / "MANIFEST.sha256.json"
    man.write_text(json.dumps(manifest, indent=1))
    os.chmod(man, 0o444)
    (snap / "MANIFEST.sha256").write_text("".join(f"{v['sha256']}  {k}\n" for k, v in manifest["files"].items()))
    os.chmod(snap / "MANIFEST.sha256", 0o444)
    for d in (snap / "ledgers", snap / "reference", snap):
        os.chmod(d, 0o555)
    print(f"frozen {len(manifest['files'])} files into {snap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
