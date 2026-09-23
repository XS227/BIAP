from __future__ import annotations

import json
import re

import requests
from bs4 import BeautifulSoup

URL = "https://live.euronext.com/en/products/equities/regulated/list"
HEADERS = {"User-Agent": "BIAP Global Euronext directory probe (+https://setai.no)"}


def main() -> None:
    session = requests.Session()
    r = session.get(URL, headers=HEADERS, timeout=45)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    forms = []
    for form in soup.find_all("form"):
        blob = " ".join(form.get("class") or []) + " " + str(form.get("id") or "")
        if "view" in blob.lower() or "equ" in blob.lower() or "product" in blob.lower():
            forms.append({
                "id": form.get("id"),
                "class": form.get("class"),
                "action": form.get("action"),
                "method": form.get("method"),
                "inputs": [
                    {"name": x.get("name"), "value": x.get("value"), "type": x.get("type")}
                    for x in form.find_all(["input", "select"])
                    if x.get("name")
                ][:80],
            })

    views = []
    for tag in soup.find_all(True):
        attrs = tag.attrs or {}
        interesting = {
            str(k): v for k, v in attrs.items()
            if any(token in str(k).lower() for token in ("view", "ajax", "drupal", "dom-id"))
        }
        classes = " ".join(attrs.get("class") or [])
        if interesting or "view-" in classes:
            record = {"tag": tag.name, "class": attrs.get("class"), "id": attrs.get("id"), **interesting}
            text = tag.get_text(" ", strip=True)
            if text:
                record["text"] = text[:180]
            views.append(record)

    script_srcs = [s.get("src") for s in soup.find_all("script") if s.get("src")]
    inline = "\n".join(s.get_text("\n") for s in soup.find_all("script") if not s.get("src"))
    urls = sorted(set(re.findall(r'''(?:(?:https?:)?//[^"'\\s]+|/[A-Za-z0-9_./?=&%-]*(?:ajax|views)[A-Za-z0-9_./?=&%-]*)''', html, flags=re.I)))
    settings_hits = []
    for line in inline.splitlines():
        low = line.lower()
        if any(x in low for x in ("views", "ajax", "equities", "regulated")):
            settings_hits.append(line.strip()[:1000])

    # Search JS assets for likely endpoint strings without dumping full assets.
    asset_hits = []
    for src in script_srcs:
        if not src:
            continue
        full = src if src.startswith("http") else "https://live.euronext.com" + (src if src.startswith("/") else "/" + src)
        try:
            jr = session.get(full, headers=HEADERS, timeout=25)
            if jr.status_code != 200 or len(jr.content) > 8_000_000:
                continue
            text = jr.text
        except Exception:
            continue
        found = sorted(set(re.findall(r'''["']([^"']*(?:views/ajax|search_instruments|equities[^"']*(?:ajax|list)|ajax[^"']*equities)[^"']*)["']''', text, flags=re.I)))
        if found:
            asset_hits.append({"src": src, "hits": found[:30]})

    print(json.dumps({
        "status": r.status_code,
        "bytes": len(r.content),
        "cookies": list(session.cookies.get_dict().keys()),
        "forms": forms[:20],
        "views": views[:100],
        "candidateUrls": urls[:100],
        "inlineSettings": settings_hits[:80],
        "assetHits": asset_hits[:40],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
