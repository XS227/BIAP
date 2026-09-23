from __future__ import annotations

import json
from urllib.parse import urlencode

import requests

BASE = "https://live.euronext.com"
MICS = "MTAA,XAMS,XBRU,XLDN,XLIS,XMSM,XOSL,XPAR"
HEADERS = {
    "User-Agent": "BIAP Global Euronext gateway probe (+https://setai.no)",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://live.euronext.com/en/products/equities/regulated/list",
    "X-Requested-With": "XMLHttpRequest",
}


def summarize(name: str, response: requests.Response) -> dict:
    item = {
        "name": name,
        "status": response.status_code,
        "contentType": response.headers.get("content-type"),
        "bytes": len(response.content),
        "url": response.url,
    }
    try:
        payload = response.json()
        item["jsonType"] = type(payload).__name__
        if isinstance(payload, dict):
            item["keys"] = list(payload.keys())[:40]
            for key in ("data", "aaData", "recordsTotal", "recordsFiltered", "iTotalRecords", "iTotalDisplayRecords", "count", "total"):
                if key in payload:
                    value = payload[key]
                    item[key] = len(value) if isinstance(value, list) else value
            rows = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("aaData")
            if isinstance(rows, list):
                item["sample"] = rows[:4]
        elif isinstance(payload, list):
            item["count"] = len(payload)
            item["sample"] = payload[:4]
    except Exception:
        item["textSample"] = response.text[:1500]
    return item


def main() -> None:
    s = requests.Session()
    page = s.get("https://live.euronext.com/en/products/equities/regulated/list", headers=HEADERS, timeout=45)
    page.raise_for_status()

    endpoint = f"{BASE}/en/product_directory/data/stocks-euronext-regulated"
    download = f"{BASE}/product_directory/data/stocks-euronext-regulated/download"

    probes = []
    variants = [
        ("bare", {"mics": MICS}),
        ("dt100", {"mics": MICS, "iDisplayStart": 0, "iDisplayLength": 100}),
        ("dt5000", {"mics": MICS, "iDisplayStart": 0, "iDisplayLength": 5000}),
        ("modern", {"mics": MICS, "start": 0, "length": 100}),
        ("paris", {"mics": "XPAR", "iDisplayStart": 0, "iDisplayLength": 100}),
        ("milan", {"mics": "MTAA", "iDisplayStart": 0, "iDisplayLength": 100}),
        ("dublin", {"mics": "XMSM", "iDisplayStart": 0, "iDisplayLength": 100}),
    ]
    for name, params in variants:
        try:
            r = s.get(endpoint, params=params, headers=HEADERS, timeout=60)
            probes.append(summarize(name, r))
        except Exception as exc:
            probes.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})

    for name, params in [
        ("download-all", {"mics": MICS}),
        ("download-paris", {"mics": "XPAR"}),
    ]:
        try:
            r = s.get(download, params=params, headers={**HEADERS, "Accept": "*/*"}, timeout=90)
            probes.append(summarize(name, r))
        except Exception as exc:
            probes.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})

    print(json.dumps(probes, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
