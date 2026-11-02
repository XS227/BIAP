"""Read-only Checkpoint 1 evidence-quality audit of verified Liara CODAL inbox.

This diagnostic deliberately never contacts CODAL or a broker, and never writes
to the inbox or historical prices. It is NOT a financial-statement validator.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.codal_inbox import Inbox

NAMED_ISSUER = re.compile(r"\(\s*شرکت\s+([^()]+)\)")

JALALI_PERIOD = re.compile(
    r"(?:سال|دوره) مالی منتهی به\s+([۰-۹٠-٩0-9]{4}/[۰-۹٠-٩0-9]{2}/[۰-۹٠-٩0-9]{2})"
)
DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def filing_metadata(title: str) -> dict:
    """Extract title claims, never independently verified accounting facts."""
    title = title or ""
    period = JALALI_PERIOD.search(title)
    if re.search(r"حسابرسی\s*نشده", title):
        assurance = "UNAUDITED"
    elif re.search(r"حسابرسی\s*شده", title):
        assurance = "AUDITED"
    else:
        assurance = "NOT_STATED"
    return {
        "scope_claim": "CONSOLIDATED" if "تلفیقی" in title else "NOT_EXPLICITLY_CONSOLIDATED",
        "assurance_claim": assurance,
        "period_end_jalali": period.group(1).translate(DIGIT_TRANSLATION) if period else None,
    }



def normalized_name(name: str) -> str:
    name = name.translate(str.maketrans({"ك": "ک", "ي": "ی", "ة": "ه"}))
    name = re.sub(r"^(?:شرکت\s+)+", "", name.strip())
    return re.sub(r"[^\w\u0600-\u06ff]", "", name).casefold()


def issuer_evidence(title: str, expected_issuer: str) -> str:
    """Classify an explicit named issuer; do not infer ownership from a title."""
    match = NAMED_ISSUER.search(title or "")
    if not match:
        return "ISSUER_NOT_EXPLICIT"
    return ("EXPLICIT_ISSUER_MATCH" if normalized_name(match.group(1)) ==
            normalized_name(expected_issuer) else "EXPLICIT_ISSUER_REVIEW")


def audit_symbol(inbox: Inbox, symbol: str) -> dict:
    record = inbox.record(symbol)
    issuer = (record.get("company") or {}).get("n") or ""
    filings = record.get("financial_filings") or []
    items = []
    for filing in filings:
        tracing_no = str(filing.get("tracing_no") or "")
        classification = issuer_evidence(str(filing.get("title") or ""), issuer)
        html_available = False
        if tracing_no:
            try:
                report_html = inbox.report_html(tracing_no)
                # Missing/malformed inbox content must fail closed, not abort
                # the whole read-only audit or be treated as financial evidence.
                html_available = isinstance(report_html, str) and bool(report_html.strip())
            except (ValueError, KeyError, OSError, RuntimeError):
                pass
        items.append({
            "tracing_no": tracing_no,
            "issuer_evidence": classification,
            "html_available": html_available,
            **filing_metadata(str(filing.get("title") or "")),
            "financial_ai_eligible": False,
            "quality_gate": (
                "BLOCKED_HTML_MISSING" if not html_available
                else "BLOCKED_ISSUER_SCOPE_AND_ACCOUNTING_NOT_RECONCILED"
            ),
        })
    return {
        "symbol": symbol,
        "issuer": issuer,
        "inbox_status": record.get("status"),
        "financial_filings": len(items),
        "explicit_issuer_review": sum(x["issuer_evidence"] == "EXPLICIT_ISSUER_REVIEW" for x in items),
        "html_available": sum(x["html_available"] for x in items),
        "html_missing": sum(not x["html_available"] for x in items),
        "audited_consolidated_html_unvalidated": sum(
            x["html_available"] and x["scope_claim"] == "CONSOLIDATED"
            and x["assurance_claim"] == "AUDITED" for x in items
        ),
        "financial_ai_eligible": False,
        "audit_status": "BLOCKED_PENDING_ISSUER_AND_STATEMENT_VALIDATION",
        "market_price_reconciliation": "NOT_POSSIBLE_FROM_CODAL_INBOX_ALONE",
        "filing_evidence": items,
    }


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
