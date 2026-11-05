"""Independent re-verification of stored CODAL statements against the ORIGINAL filing HTML in the CODAL inbox.

Why: statements stored by an older parser build can carry a wrong balance-sheet row (e.g. "جمع دارایی‌های غیرجاری"
taken for "جمع دارایی‌ها"), which breaks every ratio built on it. This tool re-reads each stored statement's own
tracing number from the verified inbox, parses it with the CURRENT parser (which rejects non-balancing sheets) and
compares. It never calls CODAL, never invents a value, and never touches market data.

  corrected   - the current parser reads different numbers from the original filing and they balance: stored numbers replaced
  verified    - the original filing yields the stored numbers
  unverified  - the filing is not in the inbox, or the current parser refuses it (balance sheet does not balance)
Statements that cannot be verified are tagged ``verification`` so downstream modules show them as unverified.

Default is a dry run; ``--apply`` writes (only ``company_json`` of the rows that changed, ``enriched_at`` untouched).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Optional

NUMERIC = ("revenue", "net_profit", "gross_profit", "total_assets", "total_liabilities", "total_equity",
           "current_assets", "current_liabilities", "receivables", "retained_earnings", "fixed_assets",
           "operating_profit", "operating_cash_flow")


def _fields(codal: dict) -> dict[str, Optional[float]]:
    return {f"{n}_{s}": codal.get(f"{n}_{s}") for n in NUMERIC for s in ("current", "prev")}


def balance_gap(codal: dict, suffix: str = "current") -> Optional[float]:
    """(assets - liabilities - equity) / |assets|, or None when an input is missing."""
    ta, tl, te = (codal.get(f"total_{k}_{suffix}") for k in ("assets", "liabilities", "equity"))
    if None in (ta, tl, te) or not ta:
        return None
    return (ta - tl - te) / abs(ta)


def verify_statement(symbol: str, codal: dict, read_html) -> dict[str, Any]:
    """Compare one stored statement with its original filing. ``read_html(tracing_no)`` returns the filing HTML."""
    from codal_data import CodalFiling
    from codal_parser_v2 import parse_fundamentals
    tracing = str(codal.get("tracing_no") or "")
    out: dict[str, Any] = {"tracingNo": tracing or None, "storedGap": balance_gap(codal)}
    if not tracing:
        return {**out, "status": "unverified", "reason": "no tracing number stored"}
    try:
        html = read_html(tracing)
    except Exception as exc:  # inbox miss: the original filing is not available locally
        return {**out, "status": "unverified", "reason": f"original filing not in the CODAL inbox ({str(exc)[:80]})"}
    filing = CodalFiling(tracing_no=tracing, title=codal.get("report_title"), sent_at=None, publish_at=None, letter_code=None,
                         url=None, pdf_url=None, excel_url=codal.get("report_url"), attachment_url=None)
    try:
        parsed = parse_fundamentals(symbol, filing, html)
    except Exception as exc:
        return {**out, "status": "unverified", "reason": f"parser error: {type(exc).__name__}"}
    if parsed is None:
        return {**out, "status": "unverified", "reason": "the original filing does not give a balancing balance sheet under the current parser"}
    new = parsed.to_dict()
    old, cur = _fields(codal), _fields(new)
    changed = {k: {"stored": old[k], "filing": cur[k]} for k in old if cur[k] is not None and old[k] != cur[k]}
    gap = balance_gap(new)
    out["filingGap"] = gap
    if gap is None:
        return {**out, "status": "unverified", "reason": "the filing does not give all three of assets, liabilities and equity"}
    if abs(gap) > 0.02:
        return {**out, "status": "unverified", "reason": "the filing's own balance sheet does not balance within 2%"}
    return {**out, "status": "corrected" if changed else "verified", "changed": changed, "values": {k: cur[k] for k in cur if cur[k] is not None}}


def reparse(db_path: str, *, apply: bool = False, inbox=None, limit: Optional[int] = None) -> dict[str, Any]:
    import codal_inbox
    inbox = inbox or codal_inbox.current()
    counts: dict[str, int] = {"verified": 0, "corrected": 0, "unverified": 0, "skipped": 0}
    details: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(db_path, timeout=60)) as conn:
        rows = conn.execute("SELECT code,symbol,company_json FROM listed_companies WHERE company_json IS NOT NULL AND company_json != ''").fetchall()
        for code, symbol, cj in rows:
            if limit is not None and len(details) >= limit:
                break
            try:
                company = json.loads(cj)
            except ValueError:
                continue
            codal = company.get("codal") if isinstance(company, dict) else None
            if not isinstance(codal, dict) or not codal.get("tracing_no"):
                counts["skipped"] += 1
                continue
            res = verify_statement(symbol, codal, inbox.report_html)
            counts[res["status"]] += 1
            details.append({"code": code, "symbol": symbol, **{k: v for k, v in res.items() if k != "values"}})
            if not apply:
                continue
            stamp = {"status": res["status"], "checkedAt": now, "method": "inbox-html-reparse", "reason": res.get("reason"),
                     "storedGap": res.get("storedGap"), "filingGap": res.get("filingGap")}
            if res["status"] == "corrected":
                codal.update(res["values"])
                stamp["changedFields"] = sorted(res["changed"])
            if codal.get("verification") != stamp or res["status"] == "corrected":
                codal["verification"] = stamp
                conn.execute("UPDATE listed_companies SET company_json=? WHERE code=?", (json.dumps(company, ensure_ascii=False, sort_keys=True), code))
        if apply:
            conn.commit()
    return {"applied": apply, "counts": counts, "details": details}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("db")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    res = reparse(a.db, apply=a.apply)
    print(json.dumps({"applied": res["applied"], "counts": res["counts"]}, ensure_ascii=False))
    for d in res["details"]:
        if d["status"] != "verified":
            print(d["status"], d["symbol"], d.get("tracingNo"), d.get("reason") or sorted((d.get("changed") or {}))[:4])


if __name__ == "__main__":
    main()
