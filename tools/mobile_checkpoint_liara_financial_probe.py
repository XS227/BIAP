#!/usr/bin/env python3
"""Read-only CODAL statement diagnostic using ONLY SHA-256 verified Liara inbox exports.

No direct CODAL/TSETMC calls, no writes to issuer DB or price history, and no
automatic promotion of extracted values into an investment decision. Parsed
accounting rows need independent scope, units, and period reconciliation.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from codal_inbox import Inbox, InboxError  # noqa: E402
from codal_data import CodalFiling  # noqa: E402
from codal_parser_v2 import parse_fundamentals  # noqa: E402



_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_UNIT_NAMES = {"میلیون": "MILLION_IRR", "هزار": "THOUSAND_IRR", "میلیارد": "BILLION_IRR"}


def filing_metadata(title: str | None, html: str) -> dict:
    """Extract *declared* report metadata; never certify accounting provenance.

    The financial title is the scope/period source. Currency units must come
    from an explicit document-wide declaration, not incidental note text.
    """
    title = str(title or "").translate(_DIGITS).replace("\u200c", " ")
    period = re.search(r"(?<!\d)(1[34]\d{2})/(\d{2})/(\d{2})(?!\d)", title)
    period_text = period.group(0) if period else None
    if "حسابرسی نشده" in title:
        audited = False
    elif "حسابرسی شده" in title:
        audited = True
    else:
        audited = None
    scope = "CONSOLIDATED" if "تلفیقی" in title else "UNVERIFIED_SCOPE"
    declared = re.search(
        r"کلیه\s+مبالغ\s+درج\s+شده\s+به\s+(میلیون|هزار|میلیارد)\s+ریال",
        html.replace("\u200c", " "),
    )
    unit = _UNIT_NAMES[declared.group(1)] if declared else None
    missing = [key for key, value in (
        ("reportPeriod", period_text), ("scope", scope if scope == "CONSOLIDATED" else None),
        ("auditStatus", audited), ("declaredUnit", unit),
    ) if value is None]
    return {
        "reportPeriodJalali": period_text,
        "scopeFromTitle": scope,
        "auditedFromTitle": audited,
        "unitDeclaredInHtml": unit,
        "metadataCompleteness": "DECLARED_METADATA_PRESENT" if not missing else "REVIEW_MISSING_METADATA",
        "missingMetadata": missing,
        "unitIndependentlyVerified": False,
        "scopeIndependentlyVerified": False,
    }


def balance_diagnostic(fundamentals) -> dict:
    fields = (fundamentals.total_assets_current,
              fundamentals.total_liabilities_current,
              fundamentals.total_equity_current)
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in fields):
        return {"status": "INCOMPLETE", "differencePctOfAssets": None}
    assets, liabilities, equity = fields
    if assets <= 0:
        return {"status": "INVALID_ASSETS", "differencePctOfAssets": None}
    gap = abs(assets - liabilities - equity) / assets * 100
    return {"status": "REVIEW_SCOPE_OR_PARSER" if gap > 1 else "ARITHMETIC_ONLY_PASS",
            "differencePctOfAssets": round(gap, 3)}


def inspect(root: Path, symbol: str) -> dict:
    inbox = Inbox(str(root))
    summary = inbox.summary()
    result = {
        "mode": "VERIFIED_LIARA_FINANCIAL_PROBE_READ_ONLY",
        "symbol": symbol,
        "verifiedExports": summary["exports"],
        "rejectedExports": len(summary["rejected"]),
        "newestExport": summary["newestExport"],
        "financialFilings": 0,
        "htmlAvailable": 0,
        "parsedReports": [],
        "missingReportHtml": 0,
        "unparseableReports": 0,
        "financialsImportApproved": False,
        "priceComparisonVerified": False,
        "checkpointReady": False,
        "directCodalRequest": False,
        "marketDataRequest": False,
        "historyModified": False,
        "reviewReason": "Independent accounting scope, report period, units and statement consistency must be verified before import.",
    }
    if summary["rejected"]:
        result["status"] = "INBOX_INTEGRITY_ERROR"
        return result
    try:
        row = inbox.record(symbol)
    except InboxError:
        result["status"] = "SYMBOL_NOT_IN_VERIFIED_INBOX"
        return result
    filings = row.get("financial_filings") or []
    result["financialFilings"] = len(filings)
    for item in filings:
        if not isinstance(item, dict) or not item.get("tracing_no"):
            result["unparseableReports"] += 1
            continue
        trace = str(item["tracing_no"])
        try:
            html = inbox.report_html(trace)
        except InboxError:
            result["missingReportHtml"] += 1
            continue
        result["htmlAvailable"] += 1
        filing = CodalFiling(**{k: item.get(k) for k in CodalFiling.__dataclass_fields__})
        parsed = parse_fundamentals(symbol, filing, html)
        if parsed is None:
            result["unparseableReports"] += 1
            continue
        result["parsedReports"].append({"tracingNo": trace, **filing_metadata(item.get("title"), html), **balance_diagnostic(parsed)})
    result["status"] = "PARSABLE_BUT_REQUIRES_RECONCILIATION" if result["parsedReports"] else "NO_PARSED_STATEMENTS"
    return result


def self_test():
    from types import SimpleNamespace
    assert balance_diagnostic(SimpleNamespace(
        total_assets_current=100, total_liabilities_current=60,
        total_equity_current=40))["status"] == "ARITHMETIC_ONLY_PASS"
    mismatch = balance_diagnostic(SimpleNamespace(
        total_assets_current=100, total_liabilities_current=60,
        total_equity_current=30))
    assert mismatch["status"] == "REVIEW_SCOPE_OR_PARSER" and mismatch["differencePctOfAssets"] == 10
    assert balance_diagnostic(SimpleNamespace(
        total_assets_current=None, total_liabilities_current=60,
        total_equity_current=40))["status"] == "INCOMPLETE"
    sample = filing_metadata(
        "صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی نشده)",
        "<div>کلیه مبالغ درج شده به میلیون ریال می باشد</div>",
    )
    assert sample["reportPeriodJalali"] == "1404/12/29"
    assert sample["scopeFromTitle"] == "CONSOLIDATED"
    assert sample["auditedFromTitle"] is False
    assert sample["unitDeclaredInHtml"] == "MILLION_IRR"
    assert sample["metadataCompleteness"] == "DECLARED_METADATA_PRESENT"
    assert not sample["unitIndependentlyVerified"]
    missing = filing_metadata("گزارش شرکت فرعی", "<p>تسهیلات میلیارد ریال</p>")
    assert missing["unitDeclaredInHtml"] is None
    assert missing["metadataCompleteness"] == "REVIEW_MISSING_METADATA"
    print("Liara-only financial reconciliation and metadata self-test: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox-root", type=Path)
    parser.add_argument("--symbol", default="پکرمان")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.inbox_root:
        parser.error("--inbox-root is required; direct CODAL access is prohibited")
    print(json.dumps(inspect(args.inbox_root, args.symbol), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
