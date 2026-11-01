#!/usr/bin/env python3
"""Read-only Pekerman CODAL evidence check from the *verified Liara inbox*.

This tool never calls CODAL, TSETMC, a trading API, or an analysis endpoint.
It does not update the inbox, company records, prices, or historical data.
The Liara inbox stores filings and report HTML, NOT a verified market quote.
Consequently, presence of a filing must never be reported as price agreement.

Usage:
  python tools/mobile_checkpoint_iran_inbox_smoke.py --inbox-root /path/to/codal-inbox
  python tools/mobile_checkpoint_iran_inbox_smoke.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from codal_inbox import Inbox, InboxError, symbol_key  # noqa: E402


def inspect_inbox(root: Path, symbol: str = "پکرمان") -> dict:
    """Only reads files through the importer that validates manifest SHA-256."""
    inbox = Inbox(str(root))
    summary = inbox.summary()
    result = {
        "mode": "LIARA_VERIFIED_INBOX_READ_ONLY",
        "symbol": symbol,
        "verifiedExports": summary["exports"],
        "newestExport": summary["newestExport"],
        "rejectedExports": len(summary["rejected"]),
        "recordStatus": "UNAVAILABLE",
        "priceComparison": "NOT_VERIFIED",
        "priceComparisonReason": "The structured Liara CODAL inbox contains filings, not an independently verified market quote.",
        "directCodalRequest": False,
        "marketDataRequest": False,
        "historyModified": False,
        "checkpointReady": False,
    }
    # Never silently trust older data when a newer export has failed integrity.
    if summary["rejected"]:
        result["recordStatus"] = "INBOX_INTEGRITY_ERROR"
        return result
    if not summary["exports"]:
        result["recordStatus"] = "NO_VERIFIED_EXPORT"
        return result
    try:
        row = inbox.record(symbol)
    except InboxError:
        raw = inbox.companies.get(symbol_key(symbol))
        result["recordStatus"] = "LIARA_FETCH_ERROR" if raw and raw.get("status") == "error" else "SYMBOL_NOT_IN_VERIFIED_INBOX"
        return result
    result["recordStatus"] = "CODAL_RECORD_PRESENT" if row["status"] == "ok" else "CODAL_NO_DATA"
    result["fetchedAt"] = row.get("fetched_at") if isinstance(row.get("fetched_at"), str) else None
    result["filingCount"] = len(row.get("filings") or []) if isinstance(row.get("filings"), list) else 0
    result["financialFilingCount"] = len(row.get("financial_filings") or []) if isinstance(row.get("financial_filings"), list) else 0
    # A report or filing is not a market quote, and its numbers are not
    # compared with prices unless a separate verified quote is supplied.
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "2026-10-31"
        folder.mkdir()
        record = {"symbol": "پكرمان", "status": "ok", "fetched_at": "2026-10-31T00:00:00Z",
                  "filings": [{"tracing_no": "test-only"}], "financial_filings": []}
        blobs = {
            "companies.jsonl": (json.dumps(record, ensure_ascii=False) + "\n").encode(),
            "reports.jsonl": b"",
            "new_filings.jsonl": b"",
        }
        manifest = {"version": 1, "files": {}}
        for name, data in blobs.items():
            (folder / name).write_bytes(data)
            manifest["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        result = inspect_inbox(root)
        assert result["recordStatus"] == "CODAL_RECORD_PRESENT", result
        assert result["priceComparison"] == "NOT_VERIFIED"
        assert result["directCodalRequest"] is False and result["historyModified"] is False
        assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
        (folder / "companies.jsonl").write_bytes(b"tampered")
        assert inspect_inbox(root)["recordStatus"] == "INBOX_INTEGRITY_ERROR"
    print("Iran Liara inbox read-only diagnostic self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox-root", type=Path)
    parser.add_argument("--symbol", default="پکرمان")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.inbox_root:
        parser.error("--inbox-root is required; never fall back to direct CODAL")
    result = inspect_inbox(args.inbox_root, args.symbol)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["recordStatus"] in ("CODAL_RECORD_PRESENT", "CODAL_NO_DATA") else 1


if __name__ == "__main__":
    raise SystemExit(main())
