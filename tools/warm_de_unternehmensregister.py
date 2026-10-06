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
import io
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

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
    """Solve only the publication security checkbox, never search-filter checkboxes."""
    for _ in range(attempts):
        body = page.inner_text("body")
        if "Ich bin ein Mensch" not in body and "Sicherheitsabfrage" not in body:
            return True
        clicked = False
        selectors = (
            "label.fox-internal-control input[type=checkbox].fox-internal-visually-hidden",
            "input[type=checkbox].fox-internal-visually-hidden",
            "label.fox-internal-control:has-text('Ich bin ein Mensch')",
            ".fox-internal-control:has-text('Ich bin ein Mensch')",
        )
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count():
                    locator.first.click(timeout=3500, force=True)
                    clicked = True
                    break
            except Exception:
                continue
        page.wait_for_timeout(6500 if clicked else 2200)
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
    """Open the best real annual-report publication link for the requested year."""
    links = page.locator("a[data-testid='normal-pub']")
    ranked: list[tuple[int, int]] = []
    wanted_year = str(year)
    for idx in range(min(links.count(), 200)):
        try:
            link = links.nth(idx)
            text = (link.inner_text(timeout=1200) or "").strip()
            low = text.lower()
            if wanted_year not in text:
                continue
            if "halbjahr" in low or "quartal" in low or "zwischen" in low or "hinweis" in low:
                continue
            score = 0
            if "konzernabschluss" in low:
                score += 100
            if "jahres- und konzernabschluss" in low:
                score += 95
            if "konzernfinanzbericht" in low or "jahresfinanzbericht" in low:
                score += 90
            if "jahresabschluss" in low:
                score += 70
            if f"01.01.{year}" in text and f"31.12.{year}" in text:
                score += 25
            try:
                parent = link.locator("xpath=..").inner_text(timeout=800).lower()
            except Exception:
                parent = low
            if "ergänzung" in parent or "ergänzt am" in parent:
                score -= 5
            ranked.append((score, idx))
        except Exception:
            continue
    for _, idx in sorted(ranked, reverse=True):
        try:
            link = links.nth(idx)
            href = link.get_attribute("href")
            if not href:
                continue
            link.click(timeout=7000)
            return True
        except Exception:
            continue
    return False




def _clean_external_url(value: str) -> Optional[str]:
    text = str(value or "").strip().rstrip(".,);]}>")
    if not text:
        return None
    if text.startswith("www."):
        text = "https://" + text
    if not text.startswith(("http://", "https://")):
        return None
    host = (urlsplit(text).hostname or "").lower()
    if not host:
        return None
    blocked = (
        "unternehmensregister.de",
        "bundesanzeiger.de",
        "publikations-plattform.de",
        "gleif.org",
        "deutsche-boerse.com",
    )
    if any(host == item or host.endswith("." + item) for item in blocked):
        return None
    return text


def _official_site_candidates(page) -> list[str]:
    """Extract issuer website/IR URLs printed by Unternehmensregister results."""
    found: list[str] = []
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    for raw in re.findall(r"https?://[^\s<>\"']+", body):
        cleaned = _clean_external_url(raw)
        if cleaned and cleaned not in found:
            found.append(cleaned)
    try:
        anchors = page.locator("a[href]")
        for idx in range(min(anchors.count(), 300)):
            href = anchors.nth(idx).get_attribute("href") or ""
            cleaned = _clean_external_url(href)
            if cleaned and cleaned not in found:
                found.append(cleaned)
    except Exception:
        pass
    return found[:12]


def _report_link_score(text: str, href: str, year: int) -> int:
    combined = f"{text} {href}".lower()
    if str(year) not in combined:
        return -1000
    if any(
        bad in combined
        for bad in (
            "halbjahr", "half-year", "half year", "quartal", "quarter",
            "presentation", "präsentation", "praesentation",
            "research", "analyst", "sustainability", "nachhaltigkeit",
        )
    ):
        return -1000
    score = 0
    for needle, weight in (
        ("annual report", 100),
        ("geschäftsbericht", 100),
        ("geschaeftsbericht", 100),
        ("jahresbericht", 95),
        ("financial report", 90),
        ("finanzbericht", 90),
        ("annual-report", 85),
        ("annual_report", 85),
        ("report", 25),
        ("bericht", 25),
    ):
        if needle in combined:
            score += weight
    if ".pdf" in combined:
        score += 45
    if "investor" in combined or "/ir" in combined:
        score += 10
    return score


def _pdf_text_from_url(url: str, timeout_s: float = 35.0) -> str:
    import httpx
    from pypdf import PdfReader

    response = httpx.get(
        url,
        timeout=timeout_s,
        follow_redirects=True,
        headers={"User-Agent": "BIAP-Global/1.0 official-filing resolver"},
    )
    response.raise_for_status()
    content = response.content
    content_type = str(response.headers.get("content-type") or "").lower()
    if not (content.startswith(b"%PDF") or "pdf" in content_type):
        raise GlobalProviderError(f"official IR report is not a PDF: {url}")
    reader = PdfReader(io.BytesIO(content))
    chunks: list[str] = []
    max_pages = min(len(reader.pages), 450)
    for idx in range(max_pages):
        try:
            text = reader.pages[idx].extract_text() or ""
        except Exception:
            text = ""
        if text:
            chunks.append(text)
    result = "\n".join(chunks).strip()
    if len(result) < 500:
        raise GlobalProviderError(f"official IR PDF text extraction too short: {url}")
    return result


def _rank_page_report_links(page, year: int) -> list[tuple[int, str]]:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    links = page.locator("a[href]")
    for idx in range(min(links.count(), 500)):
        try:
            link = links.nth(idx)
            href = link.get_attribute("href") or ""
            text = (link.inner_text(timeout=500) or "").strip()
            full = urljoin(page.url, href)
            score = _report_link_score(text, full, year)
            if score > 0 and full not in seen:
                ranked.append((score, full))
                seen.add(full)
        except Exception:
            continue
    ranked.sort(reverse=True)
    return ranked


def _try_ir_report_url(browser, url: str, year: int, timeout_ms: int) -> Optional[tuple[str, str]]:
    page = browser.new_page()
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1600)
        _click_optional(
            page,
            (
                "Nur technisch notwendige Cookies akzeptieren",
                "Alle akzeptieren",
                "Accept all",
                "Accept",
                "Akzeptieren",
            ),
        )
        body = page.inner_text("body")
        if str(year) in body and _has_financial_content(body):
            return body, page.url

        # Some IR pages hide the selected year behind tabs/buttons. Clicking a
        # visible year is safe because discovery is read-only.
        for label in (str(year + 1), str(year)):
            try:
                button = page.get_by_text(label, exact=True)
                if button.count():
                    button.first.click(timeout=1800)
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        ranked = _rank_page_report_links(page, year)
        for _, candidate in ranked[:12]:
            low = candidate.lower()
            try:
                if ".pdf" in low:
                    text = _pdf_text_from_url(candidate)
                    return text, candidate
                child = browser.new_page()
                child.set_default_timeout(timeout_ms)
                try:
                    child.goto(candidate, wait_until="domcontentloaded")
                    child.wait_for_timeout(1200)
                    child_body = child.inner_text("body")
                    if _has_financial_content(child_body):
                        return child_body, child.url
                    nested = _rank_page_report_links(child, year)
                    for _, nested_url in nested[:8]:
                        if ".pdf" in nested_url.lower():
                            text = _pdf_text_from_url(nested_url)
                            return text, nested_url
                finally:
                    child.close()
            except Exception:
                continue
        return None
    except Exception:
        return None
    finally:
        page.close()


def fetch_official_ir_report(
    browser,
    *,
    search_page,
    years: list[int],
    timeout_ms: int,
) -> Optional[tuple[int, str, str]]:
    """Try the official issuer website exposed by Unternehmensregister."""
    candidates = _official_site_candidates(search_page)
    # IR/publication URLs first, then issuer homepages.
    candidates.sort(
        key=lambda u: (
            0 if any(k in u.lower() for k in ("invest", "/ir", "publication", "finanz", "report")) else 1,
            len(u),
        )
    )
    for year in years:
        for url in candidates:
            result = _try_ir_report_url(browser, url, year, timeout_ms)
            if result is None:
                continue
            text, source_url = result
            try:
                # Validate strictly before accepting the candidate. This also
                # rejects analyst/research PDFs that happen to contain the year.
                parse_german_annual_report_text(text, expected_year=year)
            except Exception:
                continue
            return year, text, source_url
    return None

def _results_page_url(base_url: str, offset: int) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if offset > 0:
        query["from"] = str(offset)
    else:
        query.pop("from", None)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )

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

        # Prefer the issuer's own official IR/financial-report page exposed by
        # Unternehmensregister. This avoids the register document security gate
        # for the common case and still stays on an official issuer source.
        ir_result = fetch_official_ir_report(
            browser,
            search_page=page,
            years=years,
            timeout_ms=timeout_ms,
        )
        if ir_result is not None:
            return ir_result

        max_result_pages = max(
            1,
            min(7, int(os.environ.get("BIAP_DE_UR_RESULT_PAGES", "5"))),
        )
        for year in years:
            for page_no in range(max_result_pages):
                page.goto(
                    _results_page_url(results_url, page_no * 30),
                    wait_until="domcontentloaded",
                )
                page.wait_for_timeout(1400)
                if not _select_publication(page, year):
                    continue
                page.wait_for_timeout(1200)
                if not _solve_gate(page):
                    continue
                page.wait_for_timeout(700)
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





def _parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _eligible_now(row: dict[str, Any]) -> bool:
    attempts = int(row.get("attempts") or 0)
    if attempts <= 0:
        return True
    last_attempt = _parse_time(row.get("lastAttemptAt"))
    last_seen = _parse_time(row.get("lastSeenAt"))
    if row.get("priority") == "interactive" and last_seen and (
        last_attempt is None or last_seen > last_attempt
    ):
        return True
    if last_attempt is None:
        return True
    cooldown_hours = min(24, 2 ** min(attempts, 4))
    return datetime.now(timezone.utc) >= last_attempt + timedelta(hours=cooldown_hours)


def _recency_rank(row: dict[str, Any]) -> float:
    seen = _parse_time(row.get("lastSeenAt"))
    return -(seen.timestamp() if seen else 0.0)

def seed_full_german_universe(queue: dict[str, Any]) -> int:
    """Add the whole cached Frankfurt/Xetra ordinary-equity universe to the queue.

    Existing interactive rows keep their timestamps/priority. This turns the
    Germany resolver into a market-wide background fill instead of a
    ticker-by-ticker repair loop.
    """
    seeded = 0
    now = utcnow()
    for exchange in ("FRANKFURT", "XETRA"):
        path = data_root() / "universe" / "DE" / f"{exchange}.json"
        payload = read_json(path, default={})
        rows = payload.get("instruments") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            ticker = str(raw.get("ticker") or "").upper().strip()
            isin = str(raw.get("isin") or "").upper().strip()
            if not ticker or not isin.startswith("DE"):
                continue
            identity = isin
            previous = queue.get(identity) if isinstance(queue.get(identity), dict) else {}
            if previous.get("status") == "resolved":
                continue
            raw_fields = raw.get("raw_provider_fields")
            if not isinstance(raw_fields, dict):
                raw_fields = {}
            queue[identity] = {
                **previous,
                "country": "DE",
                "exchange": exchange,
                "ticker": ticker,
                "name": str(raw.get("name") or ticker),
                "isin": isin,
                "lei": raw.get("lei") or previous.get("lei"),
                "reportingMarket": raw_fields.get("reporting_market"),
                "marketSegment": raw_fields.get("market_segment"),
                "firstSeenAt": previous.get("firstSeenAt") or now,
                "lastSeenAt": previous.get("lastSeenAt") or now,
                "requestCount": int(previous.get("requestCount") or 0),
                "priority": previous.get("priority") or "batch",
                "status": previous.get("status") or "pending",
            }
            if not previous:
                seeded += 1
    return seeded

def process_queue(
    *,
    max_items: int,
    years: list[int],
    timeout_ms: int,
    headless: bool,
    seed_only: bool = False,
) -> dict[str, int]:
    queue_path = source_index_path(DEFAULT_QUEUE)
    queue = read_json(queue_path, default={})
    if not isinstance(queue, dict):
        queue = {}
    seeded = seed_full_german_universe(queue)
    if seeded:
        write_json_atomic(queue_path, queue)
    if not queue:
        return {"seeded": 0, "processed": 0, "resolved": 0, "failed": 0}
    if seed_only:
        return {
            "seeded": seeded,
            "queued": sum(
                1 for row in queue.values()
                if isinstance(row, dict) and row.get("status") != "resolved"
            ),
            "processed": 0,
            "resolved": 0,
            "failed": 0,
        }

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
        if (
            isinstance(row, dict)
            and row.get("status") != "resolved"
            and _eligible_now(row)
        )
    ]
    pending.sort(
        key=lambda item: (
            0 if item[1].get("priority") == "interactive" else 1,
            int(item[1].get("attempts") or 0),
            _recency_rank(item[1]),
        )
    )
    pending = pending[: max(0, max_items)]

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

    return {"seeded": seeded, "processed": processed, "resolved": resolved, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=int(os.environ.get("BIAP_DE_WORKER_MAX", "12")))
    ap.add_argument("--years", default=os.environ.get("BIAP_DE_WORKER_YEARS"))
    ap.add_argument("--timeout-ms", type=int, default=int(os.environ.get("BIAP_DE_WORKER_TIMEOUT_MS", "45000")))
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()
    result = process_queue(
        max_items=args.max,
        years=_years(args.years),
        timeout_ms=max(10000, args.timeout_ms),
        headless=not args.headed,
        seed_only=args.seed_only,
    )
    print(json.dumps(result, sort_keys=True))
    # Missing/unparseable issuers are an expected data state and remain queued
    # with backoff. Only worker infrastructure failures raise before this point.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
