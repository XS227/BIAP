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
    docs = (r.json().get("response") or {}).get("docs") or []
    equities = []
    for doc in docs:
        name = str(doc.get("file_name") or doc.get("download_link") or "")
        if str(doc.get("file_type") or "").upper() == "FULINS" and "FULINS_E_" in name.upper():
            equities.append({
                "publication_date": doc.get("publication_date"),
                "file_name": doc.get("file_name"),
                "download_link": doc.get("download_link"),
                "checksum": doc.get("checksum"),
            })
    equities.sort(key=lambda x: (str(x.get("publication_date") or ""), str(x.get("file_name") or "")), reverse=True)
    latest_date = str(equities[0]["publication_date"])[:10] if equities else None
    latest = sorted([x for x in equities if str(x.get("publication_date") or "")[:10] == latest_date], key=lambda x: str(x["file_name"]))
    print(json.dumps({"latest_date": latest_date, "files": latest}, indent=2))
    if not latest:
        raise SystemExit("No recent FULINS_E files found")

    wanted = {"XPAR", "XMIL", "XAMS", "XBRU", "XDUB", "XLIS"}
    found: dict[str, str] = {}
    first_raw = None

    for item in latest:
        url = item["download_link"]
        response = requests.get(url, headers={**HEADERS, "Accept": "application/zip"}, timeout=120)
        response.raise_for_status()
        print("DOWNLOAD", url, "bytes=", len(response.content), "content_type=", response.headers.get("content-type"))
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            xml_name = next(name for name in zf.namelist() if name.lower().endswith(".xml"))
            with zf.open(xml_name) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if local(elem.tag) != "RefData":
                        continue
                    raw = ET.tostring(elem, encoding="unicode")
                    if first_raw is None:
                        first_raw = raw
                    for mic in wanted - found.keys():
                        if f">{mic}<" in raw:
                            found[mic] = raw
                    elem.clear()
                    if found.keys() >= wanted:
                        break
        if found.keys() >= wanted:
            break

    print("FIRST_REFDATA_XML")
    print((first_raw or "NO_RECORD")[:12000])
    for mic in sorted(wanted):
        print(f"VENUE_{mic}_REFDATA_XML")
        print(found.get(mic, "NOT_FOUND")[:16000])
    print("FOUND_VENUES", sorted(found))


if __name__ == "__main__":
    main()
