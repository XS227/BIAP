"""Read-only Checkpoint 1 evidence-quality audit of verified Liara CODAL inbox.

Never contacts CODAL or writes to the inbox or historical prices.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.codal_inbox import Inbox
from analysis.financial_inbox_audit import audit_symbol, filing_metadata, issuer_evidence, normalized_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", required=True, help="Existing Liara inbox root (read-only)")
    parser.add_argument("--symbols", nargs="+", default=["پکرمان", "فولاد", "خودرو"])
    args = parser.parse_args()
    inbox = Inbox(args.inbox)
    print(json.dumps({
        "source": "verified_liara_codal_inbox_only",
        "inbox_summary": {k: v for k, v in inbox.summary().items() if k != "inbox"},
        "companies": [audit_symbol(inbox, s) for s in args.symbols],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
