from __future__ import annotations
import json
import requests

headers={
    "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept":"application/json, text/plain, */*",
    "Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
    "Accept-Language":"en-US,en;q=0.9",
}
urls=[
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true",
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&exchange=nasdaq",
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&exchange=nyse",
]
s=requests.Session()
for url in urls:
    try:
        r=s.get(url,headers=headers,timeout=30)
        print("URL",url,"STATUS",r.status_code,"LEN",len(r.content),"TYPE",r.headers.get("content-type"))
        print("HEAD",r.text[:300].replace("\n"," "))
        if r.ok:
            d=r.json()
            print("TOPKEYS",list(d.keys()))
            data=d.get("data") or {}
            print("DATATYPE",type(data).__name__,"KEYS",list(data.keys()) if isinstance(data,dict) else None)
            if isinstance(data,dict):
                print("TOTAL",data.get("totalrecords"))
                table=data.get("table") or {}
                rows=table.get("rows") if isinstance(table,dict) else None
                print("ROWS",len(rows or []))
                for row in (rows or [])[:5]:
                    print("ROW",json.dumps(row,ensure_ascii=False))
    except Exception as exc:
        print("ERR",type(exc).__name__,str(exc)[:300])
