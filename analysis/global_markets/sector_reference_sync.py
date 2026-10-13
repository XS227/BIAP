"""Bounded sync that builds the identifier-keyed sector reference (see sector_reference.py).

    python -m global_markets.sector_reference_sync NL FR IT BE PT NO DE ES CH GR [--limit N]

Network use is polite (serial Euronext requests, 100-ISIN Wikidata batches) and
resumable: ISINs that already have an entry are skipped unless ``--refresh``.
"""
from __future__ import annotations

import argparse
import io
import zipfile
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from .sector_reference import (
    bme_entry, classify_wikidata_industries, deutsche_boerse_entry, icb_entry, load_entries, reference_path, save_entries,
)

_EURONEXT = "https://live.euronext.com/en/ajax/getFactsheetInfoBlock/STOCK/{isin}-{mic}/fs_icb_block"
_EURONEXT_MICS = {"FR": ("XPAR",), "NL": ("XAMS",), "BE": ("XBRU",), "PT": ("XLIS",), "IT": ("XMIL", "MTAA"),
                  "NO": ("XOSL",), "IE": ("XMSM", "XDUB")}
_WIKIDATA = "https://query.wikidata.org/sparql"
_UA = "BIAP-Global/1.0 sector-reference (+https://setai.no)"
_ICB = re.compile(
    r"Industry\s+(\d{2}),\s*(.+?)\s+SuperSector\s+(\d{4}),\s*(.+?)\s+Sector\s+(\d{6}),\s*(.+?)\s+Subsector\s+(\d{8}),\s*(.+?)\s*(?:Help|$)",
    re.S,
)


def parse_euronext_icb(html: str) -> Optional[dict]:
    text = re.sub(r"<[^>]*>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    match = _ICB.search(text)
    if not match:
        return None
    return {"code": match.group(7), "industry": match.group(8).strip(), "sector": match.group(6).strip(),
            "industryName": match.group(2).strip()}


def fetch_euronext(session: requests.Session, isin: str, mics: tuple[str, ...]) -> Optional[tuple[dict, str]]:
    for mic in mics:
        url = _EURONEXT.format(isin=isin, mic=mic)
        try:
            response = session.get(url, headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}, timeout=30)
        except requests.RequestException:
            continue
        if response.status_code == 200:
            parsed = parse_euronext_icb(response.text)
            if parsed:
                return parsed, url
    return None


def fetch_wikidata(session: requests.Session, isins: list[str]) -> dict[str, list[str]]:
    values = " ".join(f'"{isin}"' for isin in isins)
    query = (
        "SELECT ?isin ?indLabel WHERE { VALUES ?isin { %s } ?c wdt:P946 ?isin. ?c wdt:P452 ?ind. "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }' % values
    )
    response = session.get(_WIKIDATA, params={"query": query}, headers={"User-Agent": _UA, "Accept": "application/sparql-results+json"}, timeout=90)
    response.raise_for_status()
    out: dict[str, list[str]] = {}
    for row in response.json()["results"]["bindings"]:
        out.setdefault(row["isin"]["value"], []).append(row["indLabel"]["value"])
    return out


_BME = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"


def fetch_bme(session: requests.Session) -> dict[str, tuple[str, str, str, str]]:
    """ISIN -> (sector code, subsector code, sector name, subsector name) for every BME-listed company."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Origin": "https://www.bolsasymercados.es"}
    names: dict[tuple[str, str], tuple[str, str]] = {}
    response = session.get(_BME + "SubsectorsAll", headers=headers, timeout=60)
    response.raise_for_status()
    for sector in response.json().get("data") or []:
        for sub in sector.get("subsectors") or []:
            names[(sector["code"], sub["code"])] = (sector["name"], sub["name"])
    out: dict[str, tuple[str, str, str, str]] = {}
    page = 0
    while True:
        response = session.get(_BME + "ListedCompanies", params={"pageSize": 100, "page": page}, headers=headers, timeout=60)
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("data") or []:
            key = (str(row.get("sector") or ""), str(row.get("subsector") or ""))
            sector_name, sub_name = names.get(key, ("", ""))
            if row.get("isin") and sector_name:
                out[str(row["isin"]).upper()] = (key[0], key[1], sector_name, sub_name)
        page += 1
        if not payload.get("hasMoreResults") or page > 60:
            return out
        time.sleep(0.2)


_DB_LANDING = "https://www.cashmarket.deutsche-boerse.com/cash-en/Data-Tech/statistics/listed-companies"
_DB_SEGMENT_SHEETS = ("Prime Standard", "General Standard", "Scale", "Basic Board")
_XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def parse_deutsche_boerse_xlsx(content: bytes) -> dict[str, tuple[str, str, str]]:
    """ISIN -> (sector, subsector, segment) from the Listed Companies workbook (stdlib only)."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    shared = [
        "".join(t.text or "" for t in si.iter(_XML_NS + "t"))
        for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(_XML_NS + "si")
    ]
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = {
        r.get("Id"): r.get("Target")
        for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    }
    out: dict[str, tuple[str, str, str]] = {}
    for sheet in workbook.find(_XML_NS + "sheets"):
        name = sheet.get("name")
        if name not in _DB_SEGMENT_SHEETS:
            continue
        target = rels[sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        for row in ET.fromstring(archive.read(path)).iter(_XML_NS + "row"):
            cells: dict[str, str] = {}
            for cell in row.findall(_XML_NS + "c"):
                value = cell.find(_XML_NS + "v")
                if value is None:
                    continue
                column = re.match(r"[A-Z]+", cell.get("r")).group()
                cells[column] = shared[int(value.text)] if cell.get("t") == "s" else value.text
            isin = (cells.get("A") or "").strip().upper()
            if _ISIN_RE.match(isin):
                out[isin] = ((cells.get("D") or "").strip(), (cells.get("E") or "").strip(), name)
    return out


def fetch_deutsche_boerse(session: requests.Session) -> tuple[dict[str, tuple[str, str, str]], str]:
    """Download the current Listed Companies workbook (the blob URL changes on republish)."""
    headers = {"User-Agent": "Mozilla/5.0 BIAP-Global/1.0 sector-reference"}
    page = session.get(_DB_LANDING, headers=headers, timeout=60)
    page.raise_for_status()
    match = re.search(r'href="([^"]*Listed-companies\.xlsx)"', page.text)
    if not match:
        raise ValueError("Listed-companies.xlsx link not found on the Deutsche Boerse page")
    url = urljoin(_DB_LANDING, match.group(1))
    response = session.get(url, headers=headers, timeout=120)
    response.raise_for_status()
    return parse_deutsche_boerse_xlsx(response.content), url


def _instruments(data_dir: Optional[str], country: str) -> list[dict]:
    root = Path(data_dir or "/var/lib/biap-global") / "universe" / country
    rows: list[dict] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in payload.get("instruments") or []:
            if isinstance(row, dict) and row.get("isin") and not str(row.get("sector") or "").strip():
                rows.append(row)
    return rows


def sync(countries: list[str], *, data_dir: Optional[str] = None, limit: Optional[int] = None, refresh: bool = False, pause: float = 0.2) -> dict:
    path = reference_path(data_dir)
    entries = dict(load_entries(path))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session = requests.Session()
    report: dict[str, dict] = {}
    for country in countries:
        country = country.upper()
        rows = _instruments(data_dir, country)
        isins = list(dict.fromkeys(str(r["isin"]).upper() for r in rows))
        db: dict = {}
        db_url = ""
        if country == "DE":
            try:
                db, db_url = fetch_deutsche_boerse(session)
            except (requests.RequestException, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
                print(f"Deutsche Boerse listed-companies fetch failed ({type(exc).__name__}); falling back to Wikidata", file=sys.stderr)
        todo = [
            i for i in isins
            if refresh or i not in entries or (db.get(i) and entries[i].get("source") == "wikidata-industry")
        ]
        if limit:
            todo = todo[:limit]
        official = wiki = missing = 0
        leftover: list[str] = []
        mics = _EURONEXT_MICS.get(country)
        bme: dict = {}
        if country == "ES":
            try:
                bme = fetch_bme(session)
            except (requests.RequestException, ValueError, KeyError) as exc:
                print(f"BME listed-companies fetch failed ({type(exc).__name__}); falling back to Wikidata", file=sys.stderr)
        for isin in todo:
            if db.get(isin):
                entry = deutsche_boerse_entry(*db[isin][:3], url=db_url, retrieved_at=now)
                if entry:
                    entries[isin] = entry
                    official += 1
                    continue
            if bme.get(isin):
                entry = bme_entry(*bme[isin][:2], *bme[isin][2:], retrieved_at=now)
                if entry:
                    entries[isin] = entry
                    official += 1
                    continue
            if mics:
                found = fetch_euronext(session, isin, mics)
                time.sleep(pause)
                if found:
                    parsed, url = found
                    entry = icb_entry(parsed["code"], parsed["industry"], parsed["sector"], url=url, retrieved_at=now)
                    if entry:
                        entries[isin] = entry
                        official += 1
                        continue
            leftover.append(isin)
        for start in range(0, len(leftover), 100):
            chunk = leftover[start:start + 100]
            try:
                labels = fetch_wikidata(session, chunk)
            except requests.RequestException as exc:
                print(f"wikidata batch failed ({type(exc).__name__}); {len(chunk)} ISINs left unclassified", file=sys.stderr)
                labels = {}
            time.sleep(1.0)
            for isin in chunk:
                verdict = classify_wikidata_industries(labels.get(isin, []))
                if verdict:
                    entries[isin] = {
                        "sector": verdict["sector"], "industry": verdict["industry"], "kind": verdict["kind"],
                        "source": "wikidata-industry",
                        "classification": "Wikidata industry (P452) of the item with this ISIN (P946); community-curated, not ICB/GICS",
                        "url": f"https://www.wikidata.org/w/index.php?search={isin}", "retrievedAt": now,
                        "evidenceLabel": verdict["label"],
                    }
                    wiki += 1
                else:
                    missing += 1
        report[country] = {"instrumentsWithoutSector": len(isins), "fetched": len(todo), "officialIcbOrExchange": official,
                           "wikidata": wiki, "unclassified": missing}
    save_entries(entries, path)
    return {"path": str(path), "totalEntries": len(entries), "markets": report}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", nargs="+")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--data-dir")
    args = parser.parse_args(argv)
    print(json.dumps(sync(args.countries, data_dir=args.data_dir, limit=args.limit, refresh=args.refresh), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
