import json,sys,os,hashlib
code,out=sys.argv[1],sys.argv[2]
os.environ['BIAP_GLOBAL_DATA_DIR']='/home/ubuntu/biap-global/overnight/data'
sys.path.insert(0,code)
from global_markets.service import analyze_company
from global_markets.models import GlobalCompany
specs=[('NO','EURONEXT_OSLO',t,'NOK') for t in ('EQNR','DNB','AKER')]+[('SE','NASDAQ_STOCKHOLM',t,'SEK') for t in ('INVE.B','ERIC.B','ATCO.A')]+[('DE','XETRA',t,'EUR') for t in ('SAP','DTE','SIE')]+[('GB','LSE',t,'GBP') for t in ('SHEL','AZN')]+[('US','NASDAQ',t,'USD') for t in ('MSFT','AAPL')]
res={}
def strip(o):
    if isinstance(o,dict): return {k:strip(v) for k,v in o.items() if k not in('retrievedAt','parsedAt','generatedAt','observed_at','fetchedAt','catalog_age_hours','priceAgeDays','fundamentalPeriodAgeDays','periodAgeDays')}
    if isinstance(o,list): return [strip(x) for x in o]
    return o
for c,e,t,cur in specs:
    try:
        r=analyze_company(GlobalCompany(country=c,exchange=e,ticker=t,name=t,currency=cur))
        s=strip(r); res[f'{c}:{t}']={'call':r['call'],'score':r['score'],'conf':r['confidence'],'ev':r['evidence']['status'],'hash':hashlib.sha256(json.dumps(s,sort_keys=True,default=str).encode()).hexdigest()[:12],'rep':r['company'].get('reporting_currency')}
    except Exception as ex: res[f'{c}:{t}']={'error':str(ex)[:120]}
json.dump(res,open(out,'w'),indent=1)
