from __future__ import annotations
import gzip
import json
import re
from urllib.parse import urljoin
import requests

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
s=requests.Session()
headers={"User-Agent":UA,"Accept":"*/*"}

def get(url,timeout=40):
    r=s.get(url,headers=headers,timeout=timeout,allow_redirects=True)
    print("GET",url,"=>",r.status_code,len(r.content),r.url,r.headers.get("content-type"))
    r.raise_for_status()
    return r

base="https://mfs.deutsche-boerse.com/DETR-posttrade"
try:
    r=get(base)
    print("DIR_HEAD",r.text[:5000])
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',r.text,re.I)
    gz=[urljoin(r.url,h) for h in hrefs if ".gz" in h.lower()]
    print("GZ_COUNT",len(gz))
    print("GZ_LAST",gz[-20:])
    if gz:
        rr=get(gz[-1],60)
        raw=gzip.decompress(rr.content)
        print("JSON_LEN",len(raw))
        print("JSON_HEAD",raw[:5000].decode("utf-8",errors="replace"))
        try:
            obj=json.loads(raw)
            print("JSON_TYPE",type(obj).__name__)
            if isinstance(obj,dict):
                print("JSON_KEYS",list(obj.keys())[:50])
        except Exception as exc:
            print("JSON_PARSE_ERR",type(exc).__name__,str(exc))
except Exception as exc:
    print("MFS_ERR",type(exc).__name__,str(exc)[:500])

# Discover static-reference download URL and print first lines/headers.
page="https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/xetra-downloads"
r=get(page)
hrefs=re.findall(r'href=["\']([^"\']+)["\']',r.text,re.I)
for token in ("t7-xetr-staticinstrumentreferencedata.csv","t7-xetr-alltradableinstruments.csv"):
    link=next((urljoin(page,h) for h in hrefs if token in h.lower()),None)
    print("TOKEN",token,"URL",link)
    if link:
        rr=get(link)
        text=rr.content.decode("utf-8-sig",errors="replace")
        print("CSV_HEAD",token)
        print("\n".join(text.splitlines()[:8]))
