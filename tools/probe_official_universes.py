from __future__ import annotations

import io
import json
import re
from urllib.parse import urljoin

import requests

UA = "BIAP-Global-official-universe-probe/1.0 (+https://setai.no)"
HEADERS = {"User-Agent": UA, "Accept": "*/*"}


def get(url: str, **kwargs):
    r = requests.get(url, headers={**HEADERS, **kwargs.pop("headers", {})}, timeout=35, **kwargs)
    r.raise_for_status()
    return r


def probe_deutsche_boerse(page_url: str, filename_token: str) -> dict:
    page = get(page_url)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', page.text, flags=re.I)
    matches = [urljoin(page_url, href) for href in hrefs if filename_token.lower() in href.lower()]
    if not matches:
        # The site occasionally renders the filename only in JSON/script data.
        raw_matches = re.findall(r'https?://[^"\'<> ]+' + re.escape(filename_token), page.text, flags=re.I)
        matches.extend(raw_matches)
    if not matches:
        raise RuntimeError(f"No {filename_token} download discovered from {page_url}")
    url = matches[0]
    data = get(url).content
    text = data.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    return {
        "page": page_url,
        "download": url,
        "bytes": len(data),
        "line_count": len(lines),
        "head": lines[:5],
    }


def probe_asx() -> dict:
    url = "https://www.asx.com.au/content/dam/asx/issuers/ISIN.xls"
    r = get(url)
    import xlrd
    book = xlrd.open_workbook(file_contents=r.content)
    out = {"download": url, "bytes": len(r.content), "sheets": []}
    for sheet in book.sheets()[:3]:
        rows = []
        for row_idx in range(min(8, sheet.nrows)):
            rows.append([sheet.cell_value(row_idx, col) for col in range(min(12, sheet.ncols))])
        out["sheets"].append({"name": sheet.name, "nrows": sheet.nrows, "ncols": sheet.ncols, "head": rows})
    return out


def probe_euronext_milan() -> dict:
    # Public Live Markets export historically backs the on-page equity directory.
    # Probe it only; do not treat it as authoritative until response fields prove
    # the regulated market can be separated from GEM/Growth/other Milan segments.
    url = (
        "https://live.euronext.com/pd/data/stocks/download"
        "?mics=XMIL&display_datapoints=dp_stocks&display_filters=df_stocks"
    )
    headers = {
        "Referer": "https://live.euronext.com/en/markets/milan/equities/euronext/list",
        "Accept": "text/csv,text/plain,*/*",
    }
    try:
        r = get(url, headers=headers)
        text = r.content.decode("utf-8-sig", errors="replace")
        lines = [line for line in text.splitlines() if line.strip()]
        return {
            "download": url,
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "bytes": len(r.content),
            "line_count": len(lines),
            "head": lines[:8],
        }
    except Exception as exc:
        return {"download": url, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    probes = {}
    for key, args in {
        "xetra": (
            "https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/xetra-downloads",
            "t7-xetr-allTradableInstruments.csv",
        ),
        "frankfurt": (
            "https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/frankfurt-downloads",
            "t7-xfra-allTradableInstruments.csv",
        ),
    }.items():
        try:
            probes[key] = probe_deutsche_boerse(*args)
        except Exception as exc:
            probes[key] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        probes["asx"] = probe_asx()
    except Exception as exc:
        probes["asx"] = {"error": f"{type(exc).__name__}: {exc}"}

    probes["euronext_milan"] = probe_euronext_milan()
    print(json.dumps(probes, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
