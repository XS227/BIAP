from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
import xml.etree.ElementTree as ET

import requests

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
HEADERS = {"User-Agent": "BIAP-Global-FIRDS-primary-venue-probe/1.0 (+https://setai.no)"}

TARGETS = {
    "FERRARI": "NL0011585146",
    "ENI": "IT0003132476",
    "APPLE": "US0378331005",
    "AGILENT": "US00846U1016",
    "LVMH": "FR0000121014",
    "TOTALENERGIES": "FR0000120271",
}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(parent: ET.Element, name: str):
    for node in list(parent):
        if local(node.tag) == name:
            return node
    return None


def text(parent: ET.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    node = child(parent, name)
    value = (node.text or "").strip() if node is not None else ""
    return value or None


def latest_files() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=20)
    params = {
        "q": "*",
        "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
        "wt": "json",
        "rows": "2000",
    }
    r = requests.get(SOLR, params=params, headers=HEADERS, timeout=45)
    r.raise_for_status()
    docs = (r.json().get("response") or {}).get("docs") or []
    rows = []
    for doc in docs:
        name = str(doc.get("file_name") or "")
        if str(doc.get("file_type") or "").upper() == "FULINS" and "FULINS_E_" in name.upper():
            rows.append(doc)
    rows.sort(key=lambda d: (str(d.get("publication_date") or ""), str(d.get("file_name") or "")), reverse=True)
    latest_date = str(rows[0].get("publication_date") or "")[:10]
    return sorted([d for d in rows if str(d.get("publication_date") or "")[:10] == latest_date], key=lambda d: str(d.get("file_name") or ""))


def parse_refdata(elem: ET.Element) -> dict:
    general = child(elem, "FinInstrmGnlAttrbts")
    venue = child(elem, "TradgVnRltdAttrbts")
    tech = child(elem, "TechAttrbts")
    return {
        "isin": text(general, "Id"),
        "fullName": text(general, "FullNm"),
        "shortName": text(general, "ShrtNm"),
        "cfi": text(general, "ClssfctnTp"),
        "currency": text(general, "NtnlCcy"),
        "actualVenue": text(venue, "Id"),
        "firstTradeDate": text(venue, "FrstTradDt"),
        "issuerLei": text(elem, "Issr"),
        "competentAuthority": text(tech, "RlvntCmptntAuthrty"),
        "relevantVenue": text(tech, "RlvntTradgVn"),
    }


def main() -> None:
    files = latest_files()
    by_isin: dict[str, list[dict]] = {isin: [] for isin in TARGETS.values()}
    wanted = set(by_isin)
    for doc in files:
        url = doc["download_link"]
        response = requests.get(url, headers=HEADERS, timeout=120)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            xml_name = next(name for name in zf.namelist() if name.lower().endswith(".xml"))
            with zf.open(xml_name) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if local(elem.tag) != "RefData":
                        continue
                    general = child(elem, "FinInstrmGnlAttrbts")
                    isin = text(general, "Id")
                    if isin in wanted:
                        by_isin[isin].append(parse_refdata(elem))
                    elem.clear()
    out = {name: by_isin[isin] for name, isin in TARGETS.items()}
    print(json.dumps(out, indent=2, ensure_ascii=False))

    # We explicitly require the key examples to exist somewhere in FIRDS.
    assert out["FERRARI"], "Ferrari ISIN missing from latest FIRDS equity files"
    assert out["ENI"], "ENI ISIN missing from latest FIRDS equity files"
    assert out["APPLE"], "Apple ISIN missing from latest FIRDS equity files"
    assert out["LVMH"], "LVMH ISIN missing from latest FIRDS equity files"


if __name__ == "__main__":
    main()
