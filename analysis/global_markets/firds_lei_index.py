"""Persistent ISIN -> issuer-LEI index from ESMA FIRDS reference data.

Why this exists
---------------
Official ESEF/OAM evidence is keyed by the issuer LEI. GLEIF's ISIN mapping is
only populated by participating numbering agencies and has no entry for many
EU issuers (e.g. Aktia Bank FI4000058870, Bank of Ireland IE00BD1RP616). The
fallback was fuzzy legal-name matching against the venue's *display* name,
which fails for abbreviations such as "BANK OF IRELAND GP" or "Aktia Pankki";
the issuer then fell through to vendor metrics and Evidence reported
``missing=fundamental_source`` although its official ESEF report existed.

ESMA FIRDS is the EU regulator's own instrument reference data: every share
admitted to an EU trading venue is reported with its issuer LEI (``Issr``).
This module keeps a small SQLite index of the weekly FULINS equity full files
so identity resolution can use ISIN -> LEI from an official source in
microseconds, without ever touching FIRDS in the request path when warm.

The LEI found here is an identity *hint*: callers still verify it against
GLEIF, and OAM/ESEF readers still require the report's own inline-XBRL entity
LEI to match before using any value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Optional
import xml.etree.ElementTree as ET
import zipfile

import requests

from .esma_firds_universe import _SOLR, _USER_AGENT, _local, parse_firds_refdata
from .providers import GlobalProviderError
from .source_cache import data_root

MAX_INDEX_AGE_DAYS = 10
_LOCK = threading.Lock()


def index_path() -> Path:
    return data_root() / "cache" / "firds-lei" / "isin_lei.sqlite3"


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path), timeout=10)


def index_metadata() -> dict:
    path = index_path()
    if not path.exists():
        return {}
    try:
        with _connect(path) as db:
            return dict(db.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return {}


def _index_age_days() -> Optional[float]:
    built = index_metadata().get("builtAt")
    if not built:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(built)).total_seconds() / 86400.0
    except ValueError:
        return None


def _latest_equity_files(timeout: float) -> tuple[str, list[str]]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=21)
    response = requests.get(
        _SOLR,
        params={
            "q": "*",
            "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
            "wt": "json",
            "rows": "2000",
        },
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    docs = (response.json().get("response") or {}).get("docs") or []
    files = [
        d for d in docs
        if isinstance(d, dict)
        and str(d.get("file_type") or "").upper() == "FULINS"
        and "FULINS_E_" in str(d.get("file_name") or "").upper()
        and d.get("download_link")
    ]
    if not files:
        raise GlobalProviderError("No recent ESMA FIRDS FULINS equity full files found")
    latest = max(str(d.get("publication_date") or "")[:10] for d in files)
    links = sorted(str(d["download_link"]) for d in files if str(d.get("publication_date") or "")[:10] == latest)
    return latest, links


def build_index(*, timeout: float = 180.0) -> dict:
    """Download the latest FIRDS equity full files and rebuild the index."""
    publication, links = _latest_equity_files(timeout)
    target = index_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    count = 0
    try:
        with _connect(tmp) as db:
            db.execute("CREATE TABLE isin_lei (isin TEXT PRIMARY KEY, lei TEXT NOT NULL, name TEXT)")
            db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            for link in links:
                response = requests.get(link, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
                response.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    xml_name = next((n for n in archive.namelist() if n.lower().endswith(".xml")), None)
                    if not xml_name:
                        raise GlobalProviderError("FIRDS equity ZIP contains no XML file")
                    batch: list[tuple[str, str, Optional[str]]] = []
                    with archive.open(xml_name) as fh:
                        for _, elem in ET.iterparse(fh, events=("end",)):
                            if _local(elem.tag) != "RefData":
                                continue
                            record = parse_firds_refdata(elem)
                            elem.clear()
                            isin = str(record.get("isin") or "").strip().upper()
                            lei = str(record.get("issuerLei") or "").strip().upper()
                            if len(isin) == 12 and len(lei) == 20:
                                batch.append((isin, lei, record.get("fullName")))
                            if len(batch) >= 5000:
                                db.executemany("INSERT OR IGNORE INTO isin_lei VALUES (?, ?, ?)", batch)
                                count += len(batch)
                                batch = []
                    db.executemany("INSERT OR IGNORE INTO isin_lei VALUES (?, ?, ?)", batch)
                    count += len(batch)
            meta = {
                "publicationDate": publication,
                "builtAt": datetime.now(timezone.utc).isoformat(),
                "files": ",".join(links),
                "rows": str(db.execute("SELECT COUNT(*) FROM isin_lei").fetchone()[0]),
            }
            db.executemany("INSERT INTO meta VALUES (?, ?)", list(meta.items()))
        if int(meta["rows"]) < 1000:
            raise GlobalProviderError(f"FIRDS ISIN->LEI index suspiciously small ({meta['rows']} rows)")
        os.replace(tmp, target)
        return meta
    finally:
        tmp.unlink(missing_ok=True)


def ensure_index(*, allow_build: bool = True) -> bool:
    """True when a usable index exists; rebuilds a missing/expired one once."""
    age = _index_age_days()
    if age is not None and age <= MAX_INDEX_AGE_DAYS:
        return True
    if not allow_build:
        return age is not None
    with _LOCK:
        age = _index_age_days()
        if age is not None and age <= MAX_INDEX_AGE_DAYS:
            return True
        try:
            build_index()
            return True
        except (requests.RequestException, GlobalProviderError, zipfile.BadZipFile, ET.ParseError, sqlite3.Error, OSError, ValueError):
            # An expired index is still regulator data; keep using it.
            return age is not None


def lookup_issuer_lei(isin: Optional[str], *, allow_build: bool = True) -> Optional[str]:
    wanted = str(isin or "").strip().upper()
    if len(wanted) != 12 or not ensure_index(allow_build=allow_build):
        return None
    try:
        with _connect(index_path()) as db:
            row = db.execute("SELECT lei FROM isin_lei WHERE isin = ?", (wanted,)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None
