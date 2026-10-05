from __future__ import annotations
import io
import json
import zipfile
import xml.etree.ElementTree as ET
import requests

from global_markets.official_universe import DeutscheBoerseUniverseProvider
from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider, parse_firds_refdata, _local

universe=list(DeutscheBoerseUniverseProvider(timeout=45).list_instruments(country="DE",exchange="XETRA"))
targets={c.isin:c for c in universe if c.isin}
print("T7_UNIVERSE",len(universe),"ISINS",len(targets))

p=ESMAFIRDSOpenFIGIUniverseProvider(timeout=60)
pub,files=p._latest_files()
print("FIRDS",pub,"FILES",len(files))
found={}
for idx,doc in enumerate(files,1):
    url=str(doc.get("download_link"))
    r=requests.get(url,headers={"User-Agent":"BIAP Global Xetra FIRDS identity audit (+https://setai.no)"},timeout=120)
    r.raise_for_status()
    z=zipfile.ZipFile(io.BytesIO(r.content))
    xml_name=next(name for name in z.namelist() if name.lower().endswith(".xml"))
    with z, z.open(xml_name) as fh:
        for _,elem in ET.iterparse(fh,events=("end",)):
            if _local(elem.tag)!="RefData":
                continue
            rec=parse_firds_refdata(elem)
            isin=str(rec.get("isin") or "").upper()
            if isin in targets:
                lei=str(rec.get("issuerLei") or "").strip().upper()
                if len(lei)==20 and lei.isalnum():
                    found.setdefault(isin,set()).add(lei)
            elem.clear()
    print("FILE",idx,"FOUND_SO_FAR",len(found))

unique={isin:next(iter(vals)) for isin,vals in found.items() if len(vals)==1}
amb={isin:sorted(vals) for isin,vals in found.items() if len(vals)>1}
print("LEI_UNIQUE",len(unique),"PCT",round(100*len(unique)/len(targets),2))
print("LEI_AMBIG",len(amb),json.dumps(list(amb.items())[:20],ensure_ascii=False))
miss=[(isin,targets[isin].ticker,targets[isin].name) for isin in targets if isin not in unique]
print("LEI_MISS",len(miss),json.dumps(miss[:50],ensure_ascii=False))

# Check whether a current ESEF/UKSEF filing exists for a representative liquid
# sample that should dominate stage-two deep analysis.
sample_tickers=["SAP","SIE","ALV","DTE","BAS","MBG","BMW","BAYN","RWE","DBK","DHL","IFX","ENR","VNA","ADS","MUV2","HNR1","CON","BEI","SDF"]
by_ticker={c.ticker:c for c in universe}
session=requests.Session()
filing_ok=0
checked=0
for ticker in sample_tickers:
    c=by_ticker.get(ticker)
    if not c or not c.isin:
        print("SAMPLE_MISSING_T7",ticker)
        continue
    lei=unique.get(c.isin)
    if not lei:
        print("SAMPLE_NO_LEI",ticker,c.isin,c.name)
        continue
    checked+=1
    url="https://filings.xbrl.org/api/filings"
    params={"filter[entity.identifier]":lei,"page[size]":5,"page[number]":1,"sort":"-period_end"}
    try:
        rr=session.get(url,params=params,headers={"Accept":"application/json","User-Agent":"BIAP Global Xetra ESEF audit"},timeout=30)
        rr.raise_for_status()
        rows=(rr.json().get("data") or [])
        de=[row for row in rows if isinstance(row,dict) and str((row.get("attributes") or {}).get("country") or "").upper()=="DE"]
        usable=[row for row in rows if isinstance(row,dict) and (row.get("attributes") or {}).get("json_url")]
        ok=bool(usable)
        filing_ok+=int(ok)
        print("SAMPLE",ticker,c.isin,lei,"FILINGS",len(rows),"DE",len(de),"USABLE",len(usable),
              "LATEST",((usable[0].get("attributes") or {}).get("period_end") if usable else None))
    except Exception as exc:
        print("SAMPLE_ERR",ticker,type(exc).__name__,str(exc)[:200])
print("SAMPLE_ESEF",filing_ok,"/",checked,"PCT",round(100*filing_ok/checked,2) if checked else 0)
