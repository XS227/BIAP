#!/usr/bin/env python3
"""Polite ESEF package discovery on an issuer's own website (robots.txt respected)."""
import json, re, sys, time, urllib.parse, urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

UA = "BIAP-Global-ESEF-discovery/1.0"
KEY = re.compile(r"invest|ir\b|/ir/|ir\.|bericht|report|publikation|publication|finanz|financ|esef|download|annual|geschaeft|jahres", re.I)
PKG = re.compile(r"\.(zip|xhtml|xbri)(\?|$)|esef", re.I)
MAX_PAGES = 90

STRONG = re.compile(r"esef|annual-report|geschaeftsbericht|geschäftsbericht|jahresfinanzbericht|financial-report|finanzbericht|publications|publikationen|berichte|reports|downloads", re.I)
def prio(u):
    return (5 if STRONG.search(u) else 0) + (2 if "2025" in u or "2026" in u else 0) + (1 if KEY.search(u) else 0) - u.count("/") * 0.1

def crawl(start, lei):
    host = urllib.parse.urlparse(start).netloc
    base_dom = ".".join(host.split(".")[-2:])
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = httpx.get(f"https://{host}/robots.txt", timeout=10, headers={"User-Agent": UA}, follow_redirects=True)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except Exception:
        rp.parse([])
    root = f"https://{host}"
    seeds = [start] + [root + p for p in ("/investor-relations", "/en/investor-relations", "/de/investor-relations", "/ir", "/en/investors", "/investors", "/de/investoren", "/investoren", "/en/ir", "/de/ir")]
    seen, queue, found = set(), seeds, {}
    client = httpx.Client(timeout=15, headers={"User-Agent": UA}, follow_redirects=True)
    while queue and len(seen) < MAX_PAGES:
        queue.sort(key=lambda u: -prio(u))
        url = queue.pop(0)
        if url in seen or not rp.can_fetch(UA, url):
            continue
        seen.add(url)
        try:
            resp = client.get(url)
        except Exception:
            continue
        if "html" not in resp.headers.get("content-type", ""):
            continue
        for href in re.findall(r'href=["\']([^"\'#]+)', resp.text):
            u = urllib.parse.urljoin(str(resp.url), href)
            p = urllib.parse.urlparse(u)
            if not p.netloc.endswith(base_dom) and not (lei and lei in u):
                continue
            if PKG.search(p.path) and not p.path.lower().endswith(".pdf"):
                score = (3 if lei and lei in u else 0) + (2 if "2025" in u else 0) + (1 if p.path.lower().endswith((".zip", ".xbri")) else 0)
                found[u] = max(found.get(u, 0), score)
            elif KEY.search(u) and u not in seen and len(queue) < 400:
                queue.append(u)
        time.sleep(0.5)
    return {"pages": len(seen), "candidates": sorted(found.items(), key=lambda x: -x[1])[:10]}

def main():
    issuers = {r["isin"]: r for r in json.load(open("issuers.json")) if r["regulated"]}
    sites = json.load(open("websites.json"))
    pick = sys.argv[1:] or list(sites)
    out_path = "crawl_results.json"
    try:
        results = json.load(open(out_path))
    except Exception:
        results = {}
    todo = [i for i in pick if i in sites and i not in results]
    def job(isin):
        r = issuers[isin]
        try:
            res = crawl(sites[isin][0], r["lei"])
        except Exception as e:
            res = {"error": str(e)[:200]}
        return isin, {**r, "site": sites[isin][0], **res}
    with ThreadPoolExecutor(32) as ex:
        for fut in as_completed([ex.submit(job, i) for i in todo]):
            isin, res = fut.result()
            results[isin] = res
            json.dump(results, open(out_path, "w"), indent=1)
            print(res["ticker"], res.get("pages"), [c[0] for c in res.get("candidates", [])[:2]], flush=True)

main()
