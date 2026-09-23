from __future__ import annotations

import json
from html import unescape
import re

import requests

BASE = "https://live.euronext.com/en/pd/data/stocks"
HEADERS = {
    "User-Agent": "Mozilla/5.0 BIAP-Global-Euronext-Probe/1.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://live.euronext.com/en/products/equities/regulated/list",
}

MARKETS = {
    "FR": "XPAR",
    "IT": "XMIL",
    "NL": "XAMS",
    "BE": "XBRU",
    "IE": "XDUB",
    "PT": "XLIS",
}


def payload(start: int = 0, length: int = 25) -> dict[str, str]:
    data = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "search[value]": "",
        "search[regex]": "false",
        "iDisplayLength": str(length),
        "iDisplayStart": str(start),
        "sSortDir_0": "asc",
        "order[0][column]": "0",
        "order[0][dir]": "asc",
    }
    for i in range(8):
        data[f"columns[{i}][data]"] = str(i)
        data[f"columns[{i}][name]"] = ""
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true" if i == 0 else "false"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"
    return data


def strip_html(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def main() -> None:
    out = {}
    session = requests.Session()
    for country, mic in MARKETS.items():
        params = {
            "mics": mic,
            "display_datapoints": "dp_stocks",
            "display_filters": "df_stocks",
        }
        try:
            r = session.post(BASE, params=params, data=payload(0, 30), headers=HEADERS, timeout=45)
            content_type = r.headers.get("content-type")
            entry = {
                "status": r.status_code,
                "content_type": content_type,
                "bytes": len(r.content),
                "prefix": r.text[:300],
            }
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                out[country] = entry
                continue
            rows = body.get("aaData") or body.get("data") or []
            entry.update({
                "keys": sorted(body.keys()),
                "recordsTotal": body.get("recordsTotal") or body.get("iTotalRecords"),
                "recordsFiltered": body.get("recordsFiltered") or body.get("iTotalDisplayRecords"),
                "row_count": len(rows) if isinstance(rows, list) else None,
                "rows": [
                    {
                        "raw": row,
                        "text": [strip_html(cell) for cell in row] if isinstance(row, list) else row,
                    }
                    for row in (rows[:8] if isinstance(rows, list) else [])
                ],
            })
            out[country] = entry
        except Exception as exc:
            out[country] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
