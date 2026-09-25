from __future__ import annotations
import gzip
import json
from urllib.parse import quote
import requests

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
s=requests.Session()
headers={"User-Agent":UA,"Accept":"application/json,*/*"}

api="https://mfs.deutsche-boerse.com/api/DETR-posttrade"
r=s.get(api,headers=headers,timeout=40)
print("API",r.status_code,len(r.content),r.url,r.headers.get("content-type"))
r.raise_for_status()
data=r.json()
print("META",json.dumps({k:data.get(k) for k in ("SrcText","DaysToKeepOnWebpage","GenerationDatetime","SourcePrefix","FileCount")},ensure_ascii=False))
files=data.get("CurrentFiles") or []
print("FILES",len(files))
print("FIRST",files[:10])
print("LAST",files[-20:])
daily=[x for x in files if "daily" in str(x).lower()]
print("DAILY",daily)
chosen=(daily[-1] if daily else files[-1])
url="https://mfs.deutsche-boerse.com/api/download/"+str(chosen).lstrip("/")
rr=s.get(url,headers={"User-Agent":UA,"Accept":"application/gzip,*/*"},timeout=90)
print("DOWNLOAD",rr.status_code,len(rr.content),rr.url,rr.headers.get("content-type"),chosen)
rr.raise_for_status()
body=rr.content
if body[:2]==b"\x1f\x8b":
    body=gzip.decompress(body)
print("RAW",len(body),body[:200])
obj=json.loads(body)
print("TYPE",type(obj).__name__)
if isinstance(obj,dict):
    print("KEYS",list(obj.keys())[:100])
    for k,v in obj.items():
        if isinstance(v,list):
            print("LIST",k,len(v))
            for row in v[:5]:
                print("ROW",k,json.dumps(row,ensure_ascii=False)[:5000])
        elif isinstance(v,dict):
            print("DICT",k,list(v.keys())[:50])
elif isinstance(obj,list):
    print("ROWS",len(obj))
    for row in obj[:10]:
        print("ROW",json.dumps(row,ensure_ascii=False)[:5000])
