from __future__ import annotations
import csv
from io import StringIO
import json
import re
import requests

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
s=requests.Session()
headers={"User-Agent":UA,"Accept":"application/json,text/plain,*/*","Referer":"https://www.nasdaq.com/market-activity/stocks/screener"}

def get_text(url):
    r=s.get(url,headers={"User-Agent":UA,"Accept":"text/plain,*/*"},timeout=30)
    r.raise_for_status()
    return r.text

def parse_pipe(text):
    lines=[x for x in text.splitlines() if x.strip() and not x.startswith("File Creation Time")]
    return list(csv.DictReader(StringIO("\n".join(lines)),delimiter="|"))

nasdaq_rows=parse_pipe(get_text("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"))
other_rows=parse_pipe(get_text("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"))
print("DIRECTORY",len(nasdaq_rows),len(other_rows),nasdaq_rows[0].keys(),other_rows[0].keys())

bad=re.compile(r"(warrant|rights?\b|units?\b|preferred|preference|depositary|depositary shares|adr\b|etf\b|etn\b|exchange traded|notes?\b|debenture|bond\b|fund\b|beneficial interest|certificate|contingent value|subscription)",re.I)

def keep_nasdaq(row):
    if (row.get("Test Issue") or "").strip().upper()=="Y": return False
    if (row.get("ETF") or "").strip().upper()=="Y": return False
    name=(row.get("Security Name") or "").strip()
    return bool(name) and not bad.search(name)

def keep_nyse(row):
    if (row.get("Exchange") or "").strip().upper()!="N": return False
    if (row.get("Test Issue") or "").strip().upper()=="Y": return False
    if (row.get("ETF") or "").strip().upper()=="Y": return False
    name=(row.get("Security Name") or "").strip()
    return bool(name) and not bad.search(name)

n=[r for r in nasdaq_rows if keep_nasdaq(r)]
y=[r for r in other_rows if keep_nyse(r)]
print("FILTERED",len(n),len(y))
print("NASDAQ_SAMPLE",json.dumps(n[:15],ensure_ascii=False))
print("NYSE_SAMPLE",json.dumps(y[:15],ensure_ascii=False))

url="https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
r=s.get(url,headers=headers,timeout=45)
r.raise_for_status()
d=r.json()
rows=((d.get("data") or {}).get("rows") or [])
print("SCREENER_ROWS",len(rows),"HEADERS",(d.get("data") or {}).get("headers"))
print("SCREENER_SAMPLE",json.dumps(rows[:5],ensure_ascii=False))
by={str(x.get("symbol") or "").strip().upper():x for x in rows}

def variants(symbol):
    s=symbol.strip().upper()
    return [s,s.replace(".","/"),s.replace("-","/"),s.replace("/","."),s.replace("^","/")]

def match(symbol):
    for v in variants(symbol):
        if v in by: return by[v]
    return None

for label,universe,symfield in [("NASDAQ",n,"Symbol"),("NYSE",y,"ACT Symbol")]:
    matched=[r for r in universe if match(r.get(symfield) or "")]
    priced=[r for r in matched if str((match(r.get(symfield) or "") or {}).get("lastsale") or "").strip() not in ("","N/A","--")]
    volume=[r for r in matched if str((match(r.get(symfield) or "") or {}).get("volume") or "").replace(",","").strip().isdigit()]
    print(label,"UNIVERSE",len(universe),"MATCHED",len(matched),"PRICED",len(priced),"VOLUME",len(volume),
          "MATCH_PCT",round(100*len(matched)/len(universe),2) if universe else 0,
          "PRICE_PCT",round(100*len(priced)/len(universe),2) if universe else 0)
    misses=[(r.get(symfield),r.get("Security Name")) for r in universe if not match(r.get(symfield) or "")]
    print(label,"MISS_SAMPLE",json.dumps(misses[:40],ensure_ascii=False))
