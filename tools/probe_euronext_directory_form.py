from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://live.euronext.com/en/products/equities/regulated/list"
HEADERS = {"User-Agent": "BIAP Global Euronext form probe (+https://setai.no)"}


def compact(value):
    if isinstance(value, list):
        return [str(x)[:240] for x in value]
    return str(value)[:1000] if value is not None else None


def main() -> None:
    s = requests.Session()
    r = s.get(URL, headers=HEADERS, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    form = soup.find("form", id=re.compile(r"awl-pd-filter-es-form", re.I)) or soup.find(
        attrs={"data-drupal-selector": re.compile(r"awl-pd-filter-es-form", re.I)}
    )
    form_info = None
    if form:
        controls = []
        for tag in form.find_all(["input", "select", "button", "textarea"]):
            item = {
                "tag": tag.name,
                "name": tag.get("name"),
                "id": tag.get("id"),
                "type": tag.get("type"),
                "value": tag.get("value"),
                "checked": tag.has_attr("checked"),
                "selected": tag.has_attr("selected"),
                "data": {k: compact(v) for k, v in tag.attrs.items() if str(k).startswith("data-")},
            }
            if tag.name == "select":
                item["options"] = [
                    {"value": o.get("value"), "text": o.get_text(" ", strip=True)[:120], "selected": o.has_attr("selected")}
                    for o in tag.find_all("option")[:100]
                ]
            controls.append(item)
        form_info = {
            "id": form.get("id"),
            "action": form.get("action"),
            "method": form.get("method"),
            "class": form.get("class"),
            "data": {k: compact(v) for k, v in form.attrs.items() if str(k).startswith("data-")},
            "controls": controls,
        }

    # Find result containers/tables and any ajax/data endpoint hints around them.
    result_nodes = []
    for tag in soup.find_all(["table", "div", "section"]):
        attrs = tag.attrs or {}
        blob = " ".join([
            str(attrs.get("id") or ""),
            " ".join(attrs.get("class") or []),
            " ".join(f"{k}={v}" for k, v in attrs.items() if str(k).startswith("data-")),
        ])
        if any(token in blob.lower() for token in ("datatable", "data-table", "product-directory", "product_directory", "pd-table", "pd-result", "awl-pd", "awl_datas")):
            result_nodes.append({
                "tag": tag.name,
                "id": attrs.get("id"),
                "class": attrs.get("class"),
                "data": {k: compact(v) for k, v in attrs.items() if str(k).startswith("data-")},
                "text": tag.get_text(" ", strip=True)[:500],
            })

    html = r.text
    contexts = []
    for needle in ("awl-pd-filter-es-form", "awl_datas_filters_es", "product_directory", "DataTable", "datatable", "ajax"):
        start = 0
        count = 0
        while count < 12:
            idx = html.lower().find(needle.lower(), start)
            if idx < 0:
                break
            contexts.append({"needle": needle, "context": html[max(0, idx-500):idx+1500]})
            start = idx + len(needle)
            count += 1

    # Inspect all same-origin JS with product/data/directory naming first, then
    # all local JS if necessary. Extract URLs/route-like strings and keywords.
    scripts = [urljoin(URL, tag.get("src")) for tag in soup.find_all("script") if tag.get("src")]
    prioritized = [u for u in scripts if any(k in u.lower() for k in ("product", "directory", "data", "awl", "pd"))]
    candidates = prioritized + [u for u in scripts if u not in prioritized]
    js_hits = []
    for src in candidates[:120]:
        try:
            jr = s.get(src, headers=HEADERS, timeout=25)
            if jr.status_code != 200 or len(jr.content) > 10_000_000:
                continue
            text = jr.text
        except Exception:
            continue
        low = text.lower()
        if not any(k in low for k in ("awl_datas", "product_directory", "pd-filter", "stocks-euronext", "regulated/list", "nameisinsym")):
            continue
        strings = sorted(set(re.findall(r'''["']([^"']{1,400})["']''', text)))
        interesting = [
            x for x in strings
            if any(k in x.lower() for k in ("ajax", "product_directory", "awl_datas", "pd-filter", "stocks-", "nameisinsym", "datatable"))
        ]
        js_hits.append({"src": src, "hits": interesting[:100]})

    print(json.dumps({
        "status": r.status_code,
        "form": form_info,
        "resultNodes": result_nodes[:80],
        "htmlContexts": contexts[:80],
        "scriptCount": len(scripts),
        "jsHits": js_hits[:30],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
