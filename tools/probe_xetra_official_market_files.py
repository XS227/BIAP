from __future__ import annotations
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
r=get(base)
html=r.text
scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I)
print("SCRIPT_COUNT",len(scripts))
for src in scripts:
    url=urljoin(r.url,src)
    print("SCRIPT",url)
    try:
        js=get(url,30).text
    except Exception as exc:
        print("SCRIPT_ERR",type(exc).__name__,str(exc)[:180])
        continue
    low=js.lower()
    if any(token in low for token in ("dynfilelist","daily-files","fetch(","ajax","json","filelist","mifid")):
        print("INTERESTING_JS",url)
        for token in ("dynFileList","daily-files","fetch(","ajax","json","fileList","serviceUrl","api"):
            idx=js.find(token)
            if idx>=0:
                print("SNIP",token,js[max(0,idx-1000):idx+2500])

print("HTML_ENDPOINT_LIKE")
for pattern in (
    r'https?://[^"\'<> ]+',
    r'["\']([^"\']*(?:json|api|files|list)[^"\']*)["\']',
):
    vals=re.findall(pattern,html,re.I)
    print(pattern, vals[:100])

page="https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/xetra-downloads"
rp=get(page)
hrefs=re.findall(r'href=["\']([^"\']+)["\']',rp.text,re.I)
print("STATIC_LIKE")
for h in hrefs:
    if any(tok in h.lower() for tok in ("static","reference","instrument")):
        print(urljoin(page,h))
