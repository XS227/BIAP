from __future__ import annotations

import json

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 BIAP-Global-Euronext-Probe/1.0",
    "Accept": "text/csv,text/plain,*/*",
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


def main() -> None:
    out = {}
    session = requests.Session()
    for country, mic in MARKETS.items():
        url = "https://live.euronext.com/en/pd/data/stocks/download"
        params = {
            "mics": mic,
            "display_datapoints": "dp_stocks",
            "display_filters": "df_stocks",
        }
        form = {
            "iDisplayLength": "10000",
            "iDisplayStart": "0",
            "args[initialLetter]": "",
            "args[fe_type]": "csv",
            "args[fe_layout]": "ver",
            "args[fe_decimal_separator]": ".",
            "args[fe_date_format]": "d/m/y",
        }
        try:
            r = session.post(url, params=params, data=form, headers=HEADERS, timeout=45, allow_redirects=True)
            text = r.content.decode("utf-8-sig", errors="replace")
            lines = [line for line in text.splitlines() if line.strip()]
            out[country] = {
                "status": r.status_code,
                "final_url": r.url,
                "content_type": r.headers.get("content-type"),
                "bytes": len(r.content),
                "line_count": len(lines),
                "head": lines[:12],
                "looks_html": text.lstrip().lower().startswith("<!doctype html") or "<html" in text[:500].lower(),
            }
        except Exception as exc:
            out[country] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
