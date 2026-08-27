"""Shared, persistent cache for CODAL audited-filing PDF text extraction.

Downloading a CODAL filing PDF and running pdftotext on it is by far the
most expensive step in CODAL enrichment, and the same filing was being
fetched repeatedly:

- across requests for the same company, since a published filing's PDF
  never changes;
- twice within a single request, because audit_parser.py and
  related_party.py each independently downloaded and pdftotext'd the same
  filing;
- across every biap-fin restart, since the previous in-process caches were
  memory-only and a restart happens on every deploy.

This module caches only the raw extracted text, keyed by the filing's
tracing_no (its stable identifier), never any classification derived from
it -- so a future audit-opinion or related-party parser bug fix always
re-runs against the same cached text instead of permanently serving an
answer computed by the old, buggy logic.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from codal_data import CodalFiling

_TIMEOUT = 20
DEFAULT_CACHE_PATH = os.environ.get(
    "BIAP_CODAL_PDF_TEXT_CACHE",
    os.path.join(os.path.dirname(__file__), "codal_pdf_text_cache.json"),
)

_lock = threading.Lock()
_memory_cache: Optional[dict[str, str]] = None


def _load() -> dict[str, str]:
    global _memory_cache
    if _memory_cache is not None:
        return _memory_cache
    try:
        with open(DEFAULT_CACHE_PATH, "r", encoding="utf-8") as handle:
            _memory_cache = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _memory_cache = {}
    return _memory_cache


def _persist(cache: dict[str, str]) -> None:
    tmp_path = f"{DEFAULT_CACHE_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False)
        os.replace(tmp_path, DEFAULT_CACHE_PATH)
    except OSError:
        # The cache is a pure optimization; a write failure must never break
        # a caller that already has its answer.
        pass


def extracted_text_for_filing(filing: CodalFiling, *, www_base: str) -> Optional[str]:
    """Return pdftotext output for filing.pdf_url, using a persistent cache.

    Returns None on any download/extraction failure, and never caches that
    None -- a transient network or environment problem is not a property of
    the (immutable) document itself, so it must not permanently poison the
    cache for a filing that could resolve successfully on a later call.
    """
    if not filing.pdf_url:
        return None

    cache_key = filing.tracing_no or filing.pdf_url

    with _lock:
        cached = _load().get(cache_key)
    if cached is not None:
        return cached

    pdf_url = urljoin(www_base, filing.pdf_url)
    req = Request(pdf_url, headers={"User-Agent": "Mozilla/5.0 BIAP/1.0"})

    try:
        with urlopen(req, timeout=_TIMEOUT) as response:
            pdf_bytes = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "filing.pdf")
            txt_path = os.path.join(tmpdir, "filing.txt")

            with open(pdf_path, "wb") as handle:
                handle.write(pdf_bytes)

            subprocess.run(
                ["pdftotext", "-layout", pdf_path, txt_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_TIMEOUT,
            )

            with open(txt_path, "r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
    except (OSError, subprocess.SubprocessError):
        return None

    with _lock:
        cache = _load()
        cache[cache_key] = text
        _persist(cache)

    return text
