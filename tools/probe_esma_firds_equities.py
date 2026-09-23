from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
import xml.etree.ElementTree as ET

import requests

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
HEADERS = {"User-Agent": "BIAP-Global-FIRDS-Probe/1.0 (+https://setai.no)", "Accept": "application/json"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_texts(element: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in element.iter():
        if node is element:
            continue
        text = (node.text or "").strip()
        if text:
            out[local(node.tag)] = text
    return out


def main() -> None:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=20)
    params = {
        "q": "*",
        "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
        "wt": "json",
        "indent": "true",
        "start": "0",
        "rows": "2000",
    }
    r = requests.get(SOLR, params=params, headers=HEADERS, timeout=45)
    r.raise_for_status()
    payload = r.json()
    docs = (payload.get("response") or {}).get("docs") or []
    equities = []
    for doc in docs:
        name = str(doc.get("file_name") or doc.get("download_link") or "")
        if str(doc.get("file_type") or "").upper() != "FULINS":
            continue
        if "FULINS_E_" not in name.upper():
            continue
        equities.append({
            "publication_date": doc.get("publication_date"),
            "file_name": doc.get("file_name"),
            "download_link": doc.get("download_link"),
            "checksum": doc.get("checksum"),
        })
    equities.sort(key=lambda x: str(x.get("publication_date") or ""), reverse=True)
    latest_date = str(equities[0]["publication_date"])[:10] if equities else None
    latest = [x for x in equities if str(x.get("publication_date") or "")[:10] == latest_date]
    print(json.dumps({"latest_date": latest_date, "files": latest}, indent=2))
    if not latest:
        raise SystemExit("No recent FULINS_E files found")

    # Inspect one current equity file so BIAP's parser is based on the current
    # official schema rather than guessed tag names.
    url = latest[0]["download_link"]
    response = requests.get(url, headers={**HEADERS, "Accept": "application/zip"}, timeout=120)
    response.raise_for_status()
    print("DOWNLOAD", url, "bytes=", len(response.content), "content_type=", response.headers.get("content-type"))
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
        print("ZIP_NAMES", names)
        xml_name = next((name for name in names if name.lower().endswith(".xml")), names[0])
        records = []
        with zf.open(xml_name) as fh:
            for event, elem in ET.iterparse(fh, events=("end",)):
                if local(elem.tag) in {"RefData", "FinInstrm", "Rcrd"}:
                    values = child_texts(elem)
                    if any(k in values for k in ("Id", "FinInstrmId", "TradgVn", "ClssfctnTp")):
                        records.append(values)
                        if len(records) >= 5:
                            break
                    elem.clear()
        print("SAMPLE_RECORDS", json.dumps(records, indent=2, ensure_ascii=False)[:12000])


if __name__ == "__main__":
    main()
