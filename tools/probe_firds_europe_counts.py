from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
import xml.etree.ElementTree as ET

import requests

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
HEADERS = {"User-Agent": "BIAP-Global-FIRDS-Europe-Probe/1.0 (+https://setai.no)"}

MARKETS = {
    "FR:EURONEXT_PARIS": ("XPAR", "EUR"),
    "IT:EURONEXT_MILAN": ("MTAA", "EUR"),
    "NL:EURONEXT_AMSTERDAM": ("XAMS", "EUR"),
    "BE:EURONEXT_BRUSSELS": ("XBRU", "EUR"),
    "IE:EURONEXT_DUBLIN": ("XDUB", "EUR"),
    "PT:EURONEXT_LISBON": ("XLIS", "EUR"),
    "SE:NASDAQ_STOCKHOLM": ("XSTO", "SEK"),
    "DK:NASDAQ_COPENHAGEN": ("XCSE", "DKK"),
    "FI:NASDAQ_HELSINKI": ("XHEL", "EUR"),
    "IS:NASDAQ_ICELAND": ("XICE", "ISK"),
    "NO:EURONEXT_OSLO": ("XOSL", "NOK"),
    "ES:BME_MADRID": ("XMAD", "EUR"),
}


def local(tag): return tag.rsplit('}',1)[-1]
def child(parent,name):
    if parent is None: return None
    return next((n for n in list(parent) if local(n.tag)==name),None)
def text(parent,name):
    n=child(parent,name); v=(n.text or '').strip() if n is not None else ''
    return v or None


def latest_files():
    today=datetime.now(timezone.utc).date(); start=today-timedelta(days=21)
    r=requests.get(SOLR,params={"q":"*","fq":f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]","wt":"json","rows":"2000"},headers=HEADERS,timeout=45)
    r.raise_for_status(); docs=(r.json().get('response') or {}).get('docs') or []
    rows=[d for d in docs if str(d.get('file_type') or '').upper()=='FULINS' and 'FULINS_E_' in str(d.get('file_name') or '').upper()]
    rows.sort(key=lambda d:(str(d.get('publication_date') or ''),str(d.get('file_name') or '')),reverse=True)
    day=str(rows[0].get('publication_date') or '')[:10]
    return day, sorted([d for d in rows if str(d.get('publication_date') or '')[:10]==day],key=lambda d:str(d.get('file_name') or ''))


def main():
    publication, files=latest_files()
    mic_map={mic:(key,currency) for key,(mic,currency) in MARKETS.items()}
    rows={key:{} for key in MARKETS}
    observed_actual=Counter(); observed_relevant=Counter()
    for doc in files:
        r=requests.get(doc['download_link'],headers=HEADERS,timeout=120); r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            name=next(n for n in zf.namelist() if n.lower().endswith('.xml'))
            with zf.open(name) as fh:
                for _,elem in ET.iterparse(fh,events=('end',)):
                    if local(elem.tag)!='RefData': continue
                    g=child(elem,'FinInstrmGnlAttrbts'); v=child(elem,'TradgVnRltdAttrbts'); t=child(elem,'TechAttrbts')
                    isin=text(g,'Id'); cfi=text(g,'ClssfctnTp') or ''; cur=text(g,'NtnlCcy'); actual=text(v,'Id'); relevant=text(t,'RlvntTradgVn')
                    if actual: observed_actual[actual]+=1
                    if relevant: observed_relevant[relevant]+=1
                    hit=mic_map.get(actual or '')
                    if hit and relevant==actual and cfi.startswith('ES') and cur==hit[1] and isin:
                        key=hit[0]
                        rows[key][isin]={"isin":isin,"name":text(g,'FullNm') or text(g,'ShrtNm'),"cfi":cfi,"mic":actual}
                    elem.clear()
    out={key:{"nativeCommonShares":len(items),"sample":list(items.values())[:8]} for key,items in rows.items()}
    print(json.dumps({"publicationDate":publication,"markets":out,"targetMicSeenActual":{mic:observed_actual[mic] for mic,_ in MARKETS.values()},"targetMicSeenRelevant":{mic:observed_relevant[mic] for mic,_ in MARKETS.values()}},indent=2,ensure_ascii=False))


if __name__=='__main__': main()
