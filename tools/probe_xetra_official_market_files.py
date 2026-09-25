from __future__ import annotations
import csv
import gzip
import io
import json
import re
from urllib.parse import urljoin
import requests

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
s=requests.Session()
headers={"User-Agent":UA,"Accept":"*/*"}

def get(url,timeout=90):
    r=s.get(url,headers=headers,timeout=timeout,allow_redirects=True)
    print("GET",url,"=>",r.status_code,len(r.content),r.url,r.headers.get("content-type"))
    r.raise_for_status()
    return r

# Official Xetra domestic common-stock ISIN universe.
page="https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads/xetra-downloads"
rp=get(page,45)
hrefs=re.findall(r'href=["\']([^"\']+)["\']',rp.text,re.I)
csv_url=next(urljoin(page,h) for h in hrefs if "t7-xetr-alltradableinstruments.csv" in h.lower())
text=get(csv_url,60).content.decode("utf-8-sig",errors="replace")
lines=[line for line in text.splitlines() if line.strip()]
hi=next(i for i,line in enumerate(lines) if line.startswith("Product Status;"))
rows=csv.DictReader(io.StringIO("\n".join(lines[hi:])),delimiter=";")
universe={}
for row in rows:
    if str(row.get("Product Status") or "").strip().upper()!="ACTIVE": continue
    if str(row.get("Instrument Status") or "").strip().upper()!="ACTIVE": continue
    if str(row.get("Instrument Type") or "").strip().upper()!="CS": continue
    if str(row.get("MIC Code") or "").strip().upper()!="XETR": continue
    if str(row.get("Currency") or row.get("Settlement Currency") or "").strip().upper()!="EUR": continue
    isin=str(row.get("ISIN") or "").strip().upper()
    if not isin.startswith("DE") or len(isin)!=12: continue
    universe[isin]={
        "ticker":str(row.get("Mnemonic") or "").strip().upper(),
        "name":str(row.get("Instrument") or "").strip(),
    }
print("UNIVERSE",len(universe))

# Official MiFIR delayed daily consolidated Xetra post-trade file.
api="https://mfs.deutsche-boerse.com/api/DETR-posttrade"
data=get(api,45).json()
daily=[x for x in (data.get("CurrentFiles") or []) if "daily" in str(x).lower()]
print("DAILY",daily)
chosen=daily[-1]
download="https://mfs.deutsche-boerse.com/api/download/"+str(chosen).lstrip("/")
rr=get(download,120)

matched=set()
trade_counts={}
quantities={}
latest={}
keyset=set()
sample=[]
total_lines=0
with gzip.GzipFile(fileobj=io.BytesIO(rr.content),mode="rb") as gz:
    for raw in gz:
        total_lines += 1
        try:
            row=json.loads(raw)
        except Exception:
            continue
        if total_lines <= 5:
            sample.append(row)
            keyset.update(row.keys())
        isin=str(row.get("instrumentIdentificationCode") or "").strip().upper()
        if isin not in universe:
            continue
        matched.add(isin)
        trade_counts[isin]=trade_counts.get(isin,0)+1
        q=None
        for key in ("quantity","tradeQuantity","volume","tradedQuantity","numberOfSecurities"):
            try:
                val=float(str(row.get(key) or "").replace(",",""))
            except Exception:
                continue
            if val>=0:
                q=val
                break
        if q is not None:
            quantities[isin]=quantities.get(isin,0.0)+q
        ts=str(row.get("publicationDateTime") or row.get("transactionDateTime") or row.get("tradeDateTime") or row.get("timestamp") or "")
        price=None
        for key in ("price","tradePrice","priceAmount"):
            try:
                val=float(str(row.get(key) or "").replace(",",""))
            except Exception:
                continue
            if val>0:
                price=val
                break
        if price is not None and (isin not in latest or ts>=latest[isin][0]):
            latest[isin]=(ts,price,row)

print("TOTAL_LINES",total_lines)
print("FIRST_KEYS",sorted(keyset))
for row in sample:
    print("SAMPLE",json.dumps(row,ensure_ascii=False))
print("MATCHED",len(matched),"PCT",round(100*len(matched)/len(universe),2))
print("WITH_PRICE",len(latest),"PCT",round(100*len(latest)/len(universe),2))
print("WITH_QTY",len(quantities),"PCT",round(100*len(quantities)/len(universe),2))
misses=[(isin,universe[isin]) for isin in universe if isin not in latest]
print("MISS_SAMPLE",json.dumps(misses[:50],ensure_ascii=False))
for isin in list(latest)[:20]:
    print("MATCH_SAMPLE",isin,universe[isin],latest[isin][0],latest[isin][1],"TRADES",trade_counts.get(isin),"QTY",quantities.get(isin),json.dumps(latest[isin][2],ensure_ascii=False))
