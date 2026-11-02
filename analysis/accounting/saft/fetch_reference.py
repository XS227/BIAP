"""Download the official Skatteetaten SAF-T Financial 1.40 reference files and verify them against reference.lock.json.

The files are public (github.com/Skatteetaten/saf-t) but the repository carries no licence file, so they are NOT committed here:
they are fetched on demand into ``reference/`` (git-ignored) and pinned by SHA-256. A changed upstream file fails loudly.

    python -m accounting.saft.fetch_reference           # fetch + verify
    python -m accounting.saft.fetch_reference --update  # re-pin after reviewing an upstream change
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_DIR = HERE / "reference"
LOCK = HERE / "reference.lock.json"
BASE = "https://raw.githubusercontent.com/Skatteetaten/saf-t/master/"
FILES = {
    "Norwegian_SAF-T_Financial_Schema_v_1.40.xsd": "SAF-T_Financial_1.4/Norwegian_SAF-T_Financial_Schema_v_1.40.xsd",
    "generated_auditfile_formatted_v_1.40.xml": "SAF-T_Financial_1.4/Example Files/generated_auditfile_formatted_v_1.40.xml",
    "About_SAF-T_Financial_schema_v.1.40.txt": "SAF-T_Financial_1.4/About_SAF-T_Financial_schema_v.1.40.txt",
    "Standard_Tax_Codes.xml": "Standard Tax Codes/XML/Standard_Tax_Codes.xml",
    "Standard_Tax_Codes.csv": "Standard Tax Codes/CSV/Standard_Tax_Codes.csv",
    "KA_K_Grouping_Category_Code.xml": "Grouping Category Code 2025-2026/XML/KA_K_Grouping_Category_Code.xml",
    "naeringsspesifikasjon.xml": "Grouping Category Code 2025-2026/XML/naeringsspesifikasjon.xml",
    "STAT_Grouping_Category_Code.xml": "Grouping Category Code 2025-2026/XML/STAT_Grouping_Category_Code.xml",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(update: bool = False) -> int:
    REF_DIR.mkdir(exist_ok=True)
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    bad = 0
    for name, path in FILES.items():
        target = REF_DIR / name
        data = target.read_bytes() if target.exists() else urllib.request.urlopen(BASE + urllib.parse.quote(path), timeout=60).read()
        digest = _sha(data)
        if update or name not in lock:
            lock[name] = digest
        elif lock[name] != digest:
            print(f"MISMATCH {name}: pinned {lock[name][:12]} got {digest[:12]}", file=sys.stderr)
            bad += 1
            continue
        target.write_bytes(data)
    if update or not LOCK.exists() or bad == 0:
        LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    raise SystemExit(1 if fetch(ap.parse_args().update) else 0)
