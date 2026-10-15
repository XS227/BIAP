import json,sys,os,sqlite3,zlib,time
os.environ['BIAP_GLOBAL_DATA_DIR']='/home/ubuntu/biap-global/overnight/data'
sys.path.insert(0,'/home/ubuntu/biap-global/wt-overnight/analysis')
from global_markets.service import analyze_company
from global_markets.models import GlobalCompany
led,out=sys.argv[1],sys.argv[2]
c=sqlite3.connect(led)
rows=[(t,json.loads(zlib.decompress(b))) for t,b in c.execute("select ticker,result from ledger where in_universe=1 and call='BUY_CANDIDATE' and evidence_status='PASS'")]
done={}
if os.path.exists(out): done=json.load(open(out))
for t,old in rows:
    if t in done: continue
    co=old['company']
    try:
        r=analyze_company(GlobalCompany(country=old['country'],exchange=old['exchange'],ticker=t,name=old.get('name') or t,currency=old.get('currency') or 'USD',isin=old.get('isin'),lei=old.get('lei')))
        n=r.get('company',{})
        done[t]={'old':{'call':old['call'],'score':old['score'],'conf':old['confidence'],'sector_pe':co.get('sector_pe'),'price':co.get('price')},
                 'new':{'call':r['call'],'score':r['score'],'conf':r['confidence'],'ev':r['evidence']['status'],'sector_pe':n.get('sector_pe'),'price':n.get('price'),'rep_ccy':n.get('reporting_currency'),
                        'gov':r.get('governance',{}).get('action'),'votes':{s['agent']:round(s['vote'],2) for s in r['signals']},'cohort':n.get('raw_provider_fields',{}).get('peer_pe_benchmark_count')}}
    except Exception as e:
        done[t]={'error':str(e)[:200]}
    json.dump(done,open(out,'w'))
print('DONE',len(done))
