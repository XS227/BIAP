from __future__ import annotations
from datetime import date, timedelta
from io import BytesIO, StringIO
import csv
import zipfile
from collections import Counter
import requests

s=requests.Session()
s.headers.update({"User-Agent":"BIAP Global official BIST probe (+https://setai.no)","Accept":"*/*"})

for delta in range(0,8):
    d=date.today()-timedelta(days=delta)
    ymd=d.strftime("%Y%m%d")
    url=f"https://borsaistanbul.com/data/thb/{d:%Y}/{d:%m}/thb{ymd}1.zip"
    r=s.get(url,timeout=10)
    print("TRY",d.isoformat(),r.status_code,len(r.content),url)
    if r.status_code!=200 or r.content[:2]!=b"PK":
        continue
    z=zipfile.ZipFile(BytesIO(r.content))
    raw=z.read(z.namelist()[0])
    text=raw.decode("cp1254",errors="replace")
    lines=text.splitlines()
    header_en=lines[1].split(";")
    rows=list(csv.DictReader(StringIO("\n".join([lines[1],*lines[2:]])),delimiter=";"))
    print("SUCCESS",url,"rows",len(rows))
    group=Counter((row.get("INSTRUMENT GROUP") or "").strip() for row in rows)
    typ=Counter((row.get("INSTRUMENT TYPE") or "").strip() for row in rows)
    print("GROUPS",group.most_common(20))
    print("TYPES",typ.most_common(20))
    eqt=[row for row in rows if (row.get("INSTRUMENT GROUP") or "").strip()=="EQT"]
    eqt_e=[row for row in eqt if (row.get("INSTRUMENT SERIES CODE") or "").strip().endswith(".E")]
    print("EQT",len(eqt),"EQT_DOT_E",len(eqt_e),"UNIQUE_BASE",len({(r["INSTRUMENT SERIES CODE"].rsplit(".",1)[0]) for r in eqt_e}))
    print("MARKET_SEGMENTS",Counter((r.get("MARKET SEGMENT") or "").strip() for r in eqt_e).most_common())
    print("MARKETS",Counter((r.get("MARKET") or "").strip() for r in eqt_e).most_common())
    for row in eqt_e[:20]:
        print("EQUITY",row.get("INSTRUMENT SERIES CODE"),row.get("INSTRUMENT NAME"),row.get("CLOSING PRICE"),row.get("TOTAL TRADED VOLUME"),row.get("MARKET SEGMENT"),row.get("MARKET"))
    raise SystemExit(0)
raise SystemExit("No bulletin found")
