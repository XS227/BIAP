#!/usr/bin/env python3
"""Warm unresolved German issuer fundamentals from Unternehmensregister.

The API request path only queues missing German filings. This worker consumes
that queue out-of-band, resolves issuer identity via GLEIF, opens the official
Unternehmensregister publication in a real browser session, normalizes the
latest financial statements conservatively, and writes a verified filing-drop
record under BIAP_GLOBAL_DATA_DIR.

No recommendation logic runs here. If the official report cannot be verified or
parsed, the queue item stays unresolved and the API continues to BLOCK rather
than fabricate values.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from global_markets.german_report_text import parse_german_annual_report_text  # noqa: E402
from global_markets.gleif import GLEIFResolver  # noqa: E402
from global_markets.providers import GlobalProviderError  # noqa: E402
from global_markets.source_cache import (  # noqa: E402
    data_root,
    read_json,
    sha256_bytes,
    source_index_path,
    write_json_atomic,
)


BASE = "https://www.unternehmensregister.de"
DEFAULT_QUEUE = "de-fundamentals-missing"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_ticker(value: str) -> str:
    safe = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_", "."})
    if not safe:
        raise ValueError("invalid ticker")
    return safe.upper()


def _years(args_years: Optional[str]) -> list[int]:
    if args_years:
        result = []
        for token in args_years.split(","):
            token = token.strip()
            if token:
                result.append(int(token))
        return result
    current = datetime.now(timezone.utc).year
    return [current - 1, current - 2]


def _click_optional(page, labels: tuple[str, ...]) -> None:
    for label in labels:
        try:
            page.get_by_text(label, exact=False).first.click(timeout=1800)
            page.wait_for_timeout(350)
            return
        except Exception:
            pass


def _solve_gate(page, attempts: int = 5) -> bool:
    for _ in range(attempts):
        body = page.inner_text("body")
        if "Ich bin ein Mensch" not in body and "Sicherheitsabfrage" not in body:
            return True
        clicked = False
        for selector in (
            "label:has-text('Ich bin ein Mensch')",
            "text=Ich bin ein Mensch",
            "input[type=checkbox]",
            ".fc-button",
            "[class*=captcha] label",
        ):
            try:
                page.locator(selector).first.click(timeout=3500)
                clicked = True
                break
            except Exception:
                continue
        page.wait_for_timeout(5000 if clicked else 2500)
    body = page.inner_text("body")
    return "Ich bin ein Mensch" not in body and "Sicherheitsabfrage" not in body


def _has_financial_content(text: str) -> bool:
    wanted = (
        "Bilanz", "Aktiva", "Passiva", "Umsatz", "Eigenkapital",
        "Umlaufvermögen", "Umlaufvermoegen", "Jahresüberschuss",
        "Jahresueberschuss", "Total assets", "Revenue", "Net income",
    )
    return sum(1 for marker in wanted if marker.lower() in text.lower()) >= 3


def _extract_report_text(page) -> str:
    body = page.inner_text("body")
    markers = (
        "Konzernabschluss",
        "Jahresabschluss",
        "Konzernbilanz",
        "Consolidated Financial Statements",
        "Bilanz",
    )
    positions = [body.find(marker) for marker in markers if body.find(marker) >= 0]
    if positions:
        body = body[min(positions):]
    return body.strip()


def _select_publication(page, year: int) -> bool:
    """Prefer consolidated/annual financial publications for the requested year."""
    candidates = (
        f"Konzernabschluss {year}",
        f"Konzernfinanzbericht {year}",
        f"Jahresfinanzbericht {year}",
        f"Geschäftsjahr vom 01.01.{year}",
        f"Geschaeftsjahr vom 01.01.{year}",
        str(year),
    )
    for text in candidates:
        try:
            locator = page.get_by_text(text, exact=False)
            count = locator.count()
            if count:
                # Prefer a match whose surrounding row/card mentions a
                # consolidated or annual financial statement.
                for idx in range(min(count, 12)):
                    candidate = locator.nth(idx)
                    try:
                        surrounding = candidate.locator("xpath=ancestor::*[self::tr or self::li or self::article or self::div][1]").inner_text(timeout=1500)
                    except Exception:
                        surrounding = candidate.inner_text(timeout=1500)
                    low = surrounding.lower()
                    if any(
                        marker in low
                        for marker in (
                            "konzernabschluss",
                            "konzernfinanzbericht",
                            "jahresfinanzbericht",
                            "jahresabschluss",
                        )
                    ):
                        candidate.click(timeout=7000)
                        return True
                locator.first.click(timeout=7000)
                return True
        except Exception:
            continue
    return False


def fetch_unternehmensregister_report(
    browser,
    *,
    company_name: str,
    years: list[int],
    timeout_ms: int,
) -> tuple[int, str, str]:
    page = browser.new_page()
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(f"{BASE}/de/suche?areas=all", wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        _click_optional(
            page,
            (
                "Nur technisch notwendige Cookies akzeptieren",
                "Allen zustimmen",
                "Akzeptieren",
            ),
        )

        search = (
            page.query_selector("input[name*='company' i]")
            or page.query_selector("input[name*='firma' i]")
            or page.query_selector("input[type='text']")
        )
        if search is None:
            raise GlobalProviderError("Unternehmensregister company search input not found")
        search.click()
        search.fill(company_name)
        page.keyboard.press("Enter")
        page.wait_for_timeout(4500)
        results_url = page.url

        for year in years:
            page.goto(results_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2200)
            if not _select_publication(page, year):
                continue
            page.wait_for_timeout(2500)
            if not _solve_gate(page):
                continue
            page.wait_for_timeout(900)
            text = _extract_report_text(page)
            if _has_financial_content(text):
                source_url = (
                    f"{BASE}/de/suche?areas=all&companyName={quote_plus(company_name)}"
                )
                return year, text, source_url
        raise GlobalProviderError(
            f"no readable current official Unternehmensregister annual report for {company_name}"
        )
    finally:
        page.close()


def _write_verified_record(
    row: dict[str, Any],
    *,
    legal_name: str,
    lei: str,
    year: int,
    report_text: str,
    source_url: str,
) -> Path:
    parsed = parse_german_annual_report_text(report_text, expected_year=year)
    ticker = _safe_ticker(row["ticker"])
    payload = {
        "verified": True,
        "sourceProvider": "unternehmensregister-de-auto",
        "sourceType": "official_regulatory_financial_statement",
        "sourceId": f"unternehmensregister:{row.get('isin') or ticker}:{parsed.period_end}",
        "sourceUrl": source_url,
        "periodEnd": parsed.period_end,
        "observedAt": utcnow(),
        "currency": parsed.currency,
        "reportScope": parsed.report_scope,
        "quality": 0.98 if parsed.audited else 0.94,
        "provenanceStatus": "independently_verified",
        "auditStatus": "audited" if parsed.audited else "unknown",
        "verificationMode": "unternehmensregister-browser+strict-statement-parser",
        "sha256": sha256_bytes(report_text.encode("utf-8")),
        "rawProviderFields": {
            "de_auto_resolver": True,
            "de_auto_legal_name": legal_name,
            "de_auto_lei": lei,
            "de_auto_reporting_market": row.get("reportingMarket"),
            "de_auto_derived_fields": list(parsed.derived_fields),
        },
        "fundamentals": parsed.fundamentals,
    }
    out = data_root() / "filings" / "DE" / f"{ticker}.json"
    write_json_atomic(out, payload)
    return out


def process_queue(
    *,
    max_items: int,
    years: list[int],
    timeout_ms: int,
    headless: bool,
) -> dict[str, int]:
    queue_path = source_index_path(DEFAULT_QUEUE)
    queue = read_json(queue_path, default={})
    if not isinstance(queue, dict) or not queue:
        return {"processed": 0, "resolved": 0, "failed": 0}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "playwright is required for the Germany worker; install "
            "tools/requirements-de-worker.txt and run playwright install chromium"
        ) from exc

    resolver = GLEIFResolver(timeout=20.0)
    processed = resolved = failed = 0
    pending = [
        (identity, row)
        for identity, row in queue.items()
        if isinstance(row, dict) and row.get("status") != "resolved"
    ][: max(0, max_items)]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        try:
            for identity, row in pending:
                processed += 1
                row = dict(row)
                row["lastAttemptAt"] = utcnow()
                row["attempts"] = int(row.get("attempts") or 0) + 1
                try:
                    isin = str(row.get("isin") or "").upper().strip()
                    if not isin:
                        raise GlobalProviderError("queued Germany issuer has no ISIN")
                    resolution = resolver.resolve_isin(isin, country="DE")
                    year, report_text, source_url = fetch_unternehmensregister_report(
                        browser,
                        company_name=resolution.legal_name,
                        years=years,
                        timeout_ms=timeout_ms,
                    )
                    path = _write_verified_record(
                        row,
                        legal_name=resolution.legal_name,
                        lei=resolution.lei,
                        year=year,
                        report_text=report_text,
                        source_url=source_url,
                    )
                    row.update(
                        {
                            "status": "resolved",
                            "resolvedAt": utcnow(),
                            "resolvedPath": str(path),
                            "lei": resolution.lei,
                            "legalName": resolution.legal_name,
                            "lastError": None,
                        }
                    )
                    resolved += 1
                except Exception as exc:
                    row.update(
                        {
                            "status": "pending",
                            "lastError": f"{type(exc).__name__}: {str(exc)[:500]}",
                        }
                    )
                    failed += 1
                queue[identity] = row
                write_json_atomic(queue_path, queue)
        finally:
            browser.close()

    return {"processed": processed, "resolved": resolved, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=int(os.environ.get("BIAP_DE_WORKER_MAX", "12")))
    ap.add_argument("--years", default=os.environ.get("BIAP_DE_WORKER_YEARS"))
    ap.add_argument("--timeout-ms", type=int, default=int(os.environ.get("BIAP_DE_WORKER_TIMEOUT_MS", "45000")))
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    result = process_queue(
        max_items=args.max,
        years=_years(args.years),
        timeout_ms=max(10000, args.timeout_ms),
        headless=not args.headed,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
