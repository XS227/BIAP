"""Load CODAL data that the Liara fetcher (tools/liara_codal_fetcher.py) delivered to a local inbox.

The BIAP VPS cannot reach codal.ir, so when ``BIAP_CODAL_INBOX`` is set the listed-company job reads
CODAL answers from dated export folders instead of calling CODAL (see the guards in codal_data.py).
Unset = disabled = the previous live behaviour.

Layout: <inbox>/YYYY-MM-DD/{manifest.json, companies.jsonl, reports.jsonl, new_filings.jsonl}.

An export is used only if its manifest verifies: every listed file must exist with the recorded
size and SHA-256. A folder that fails (half-copied by scp, edited, wrong version) is skipped and
reported in ``summary()["rejected"]``; it is never partially trusted. Verified exports are merged
oldest to newest, per symbol the newest answer wins, except that a newer ``error`` record (the
fetcher could not get an answer) never replaces an older ``ok``/``no_data`` one.

Memory: financial-statement HTML is large, so reports are indexed by file offset during the
verification pass and read back one at a time.

CLI:
  codal_inbox.py verify            # verify every export, print the summary
  codal_inbox.py request [--limit N]   # write <inbox>/request/symbols.txt (backlog for the fetcher)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
import threading
from typing import Any, Optional

ENV_VAR = "BIAP_CODAL_INBOX"
MANIFEST_VERSION = 1
MISS_MARKER = "CODAL_INBOX_MISS"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_USABLE = ("ok", "no_data")
_FILES = ("companies.jsonl", "reports.jsonl", "new_filings.jsonl")


def inbox_dir() -> Optional[str]:
    value = os.getenv(ENV_VAR, "").strip()
    return value or None


def enabled() -> bool:
    return inbox_dir() is not None


def symbol_key(value: Any) -> str:
    """Spelling-insensitive key: Arabic/Persian ي ك, ZWNJ and spaces do not distinguish symbols."""
    text = str(value or "").translate(str.maketrans({"ي": "ی", "ك": "ک"}))
    return re.sub(r"[‌‍‎‏\s]+", "", text)


class InboxError(RuntimeError):
    pass


def _verify_export(folder: str) -> dict:
    """Return the manifest of ``folder`` if every file matches it, else raise InboxError."""
    try:
        with open(os.path.join(folder, "manifest.json"), "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        raise InboxError(f"manifest unreadable: {exc}")
    if not isinstance(manifest, dict) or manifest.get("version") != MANIFEST_VERSION:
        raise InboxError(f"unsupported manifest version {manifest.get('version') if isinstance(manifest, dict) else None}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not set(_FILES) <= set(files):
        raise InboxError("manifest does not list the expected files")
    for name in _FILES:
        meta = files[name]
        path = os.path.join(folder, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            raise InboxError(f"{name} missing")
        if size != meta.get("bytes"):
            raise InboxError(f"{name} size {size} != manifest {meta.get('bytes')} (incomplete copy?)")
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != meta.get("sha256"):
            raise InboxError(f"{name} sha256 mismatch")
    return manifest


def _jsonl(path: str):
    with open(path, "rb") as handle:
        offset = 0
        for line in handle:
            if line.strip():
                yield offset, json.loads(line.decode("utf-8"))
            offset += len(line)


class Inbox:
    def __init__(self, root: str) -> None:
        self.root = root
        self.companies: dict[str, dict] = {}
        self._reports: dict[str, tuple[str, int]] = {}
        self._new_filings: list[dict] = []
        self.exports: list[dict] = []
        self.rejected: list[dict] = []
        self.new_filings_through: Optional[str] = None
        try:
            names = sorted(n for n in os.listdir(root) if _DAY.match(n) and os.path.isdir(os.path.join(root, n)))
        except OSError:
            names = []
        for name in names:
            folder = os.path.join(root, name)
            try:
                manifest = _verify_export(folder)
                self._merge(folder, name, manifest)
            except (InboxError, ValueError, KeyError, TypeError) as exc:
                self.rejected.append({"date": name, "reason": str(exc)[:200]})

    def _merge(self, folder: str, name: str, manifest: dict) -> None:
        # Parse everything before mutating, so one bad file rejects the whole export.
        companies = [row for _, row in _jsonl(os.path.join(folder, "companies.jsonl"))]
        reports = [(row["tracing_no"], offset) for offset, row in _jsonl(os.path.join(folder, "reports.jsonl"))
                   if row.get("tracing_no")]
        new_filings = [row for _, row in _jsonl(os.path.join(folder, "new_filings.jsonl"))]
        for row in companies:
            key = symbol_key(row["symbol"])
            previous = self.companies.get(key)
            if row["status"] == "error" and previous and previous["status"] in _USABLE:
                continue
            self.companies[key] = row
        for tracing_no, offset in reports:
            self._reports[tracing_no] = (os.path.join(folder, "reports.jsonl"), offset)
        self._new_filings.extend(new_filings)
        window = manifest.get("new_filings") or {}
        if window.get("complete") and window.get("through"):
            self.new_filings_through = max(self.new_filings_through or "", window["through"])
        self.exports.append({"date": name, "complete": bool(manifest.get("complete")),
                             "counts": manifest.get("counts", {}), "stopReason": manifest.get("stop_reason")})

    # --- queries used by codal_data ----------------------------------------------------------

    def record(self, symbol: str) -> dict:
        """The usable (ok / no_data) record for ``symbol``, or raise a miss."""
        row = self.companies.get(symbol_key(symbol))
        if row is None:
            raise InboxError(f"{MISS_MARKER}: {symbol} is not in the CODAL inbox yet")
        if row["status"] not in _USABLE:
            raise InboxError(f"{MISS_MARKER}: the fetcher could not get CODAL data for {symbol} ({str(row.get('error'))[:120]})")
        return row

    def has_record(self, symbol: str) -> bool:
        row = self.companies.get(symbol_key(symbol))
        return bool(row and row["status"] in _USABLE)

    def report_html(self, tracing_no: Optional[str]) -> str:
        location = self._reports.get(tracing_no or "")
        if location is None:
            raise InboxError(f"{MISS_MARKER}: no report {tracing_no} in the CODAL inbox")
        path, offset = location
        with open(path, "rb") as handle:
            handle.seek(offset)
            return json.loads(handle.readline().decode("utf-8"))["html"]

    def directory(self) -> list[dict]:
        return [row["company"] for row in self.companies.values() if row["status"] == "ok" and row.get("company")]

    def new_filing_symbols(self, since_jalali: str) -> set[str]:
        return {row["symbol"] for row in self._new_filings
                if row.get("symbol") and (row.get("sent_at") or "")[:10] >= since_jalali}

    def summary(self) -> dict:
        usable = sum(1 for r in self.companies.values() if r["status"] in _USABLE)
        newest = self.exports[-1]["date"] if self.exports else None
        age = None
        if newest:
            age = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.date.fromisoformat(newest)).days
        return {"inbox": self.root, "exports": len(self.exports), "newestExport": newest, "newestExportAgeDays": age,
                "companiesUsable": usable, "companiesTotal": len(self.companies), "reports": len(self._reports),
                "newFilingsThrough": self.new_filings_through, "rejected": self.rejected}


# --- process-wide instance ---------------------------------------------------------------------

_lock = threading.Lock()
_cached: Optional[tuple[str, tuple, Inbox]] = None


def _fingerprint(root: str) -> tuple:
    parts = []
    try:
        for name in sorted(os.listdir(root)):
            manifest = os.path.join(root, name, "manifest.json")
            if _DAY.match(name) and os.path.exists(manifest):
                st = os.stat(manifest)
                parts.append((name, st.st_mtime_ns, st.st_size))
    except OSError:
        pass
    return tuple(parts)


def current() -> Inbox:
    """The verified inbox, rebuilt only when a manifest appears or changes."""
    global _cached
    root = inbox_dir()
    if root is None:
        raise InboxError("BIAP_CODAL_INBOX is not set")
    with _lock:
        fingerprint = _fingerprint(root)
        if _cached is None or _cached[0] != root or _cached[1] != fingerprint:
            _cached = (root, fingerprint, Inbox(root))
        return _cached[2]


def reset() -> None:
    global _cached
    with _lock:
        _cached = None


def summary() -> Optional[dict]:
    return current().summary() if enabled() else None


# --- request list for the fetcher --------------------------------------------------------------

def write_request(root: str, symbols: list[str]) -> str:
    folder = os.path.join(root, "request")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "symbols.txt")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write("\n".join(symbols) + ("\n" if symbols else ""))
    os.replace(tmp, path)
    return path


def backlog_symbols(limit: int) -> list[str]:
    """Symbols of never-enriched primary companies (the daily job's backlog), without a usable inbox answer."""
    from company_registry_store import CompanyRegistryStore
    from listed_company_store import ListedCompanyStore

    store = ListedCompanyStore()
    registry = CompanyRegistryStore(store.db_path)
    codes = registry.primary_company_codes() or []
    never_enriched, _ = store._split_by_enrichment(codes)
    have = current() if enabled() else None
    out: list[str] = []
    for code in never_enriched:
        instrument = registry.get_instrument(code)
        symbol = str((instrument or {}).get("symbol") or "").strip()
        if symbol and not (have and have.has_record(symbol)) and symbol not in out:
            out.append(symbol)
        if len(out) >= limit:
            break
    return out


def main(argv: list[str]) -> int:
    root = inbox_dir()
    if root is None:
        print(f"{ENV_VAR} is not set", file=sys.stderr)
        return 2
    if argv[:1] == ["verify"]:
        print(json.dumps(current().summary(), ensure_ascii=False, indent=2))
        return 1 if current().rejected else 0
    if argv[:1] == ["request"]:
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 400
        symbols = backlog_symbols(limit)
        print(f"wrote {len(symbols)} symbols to {write_request(root, symbols)}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
