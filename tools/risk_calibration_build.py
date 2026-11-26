import json,glob,os,collections
D='/home/ubuntu/biap-global/staging-20261123/data'
uni={}
for ex in('NASDAQ','NYSE'):
    for i in json.load(open(f'{D}/universe/US/{ex}.json'))['instruments']:
        uni[(ex,i['ticker'])]=i
rows=[]
for l in open('/home/ubuntu/claude-tmpdir/risk_universe_new.jsonl'):
    r=json.loads(l)
    if r['_country']!='US' or 'error' in r: continue
    ex,t=r['_exchange'],r['_ticker']
    sig={s['id']:s for s in r['signals']}
    # fundamentals
    mc=sec=None;eq=None
    dirs=glob.glob(f'{D}/fundamentals/US/{ex}/{t}-*/latest.json')
    f={}
    if dirs:
        try: f=json.load(open(dirs[0])).get('fundamentals',{})
        except: pass
    sh=f.get('shares_outstanding'); sec=f.get('sector')
    px=None
    for h in glob.glob(f'{D}/history/US/{ex}/{t}/*.json'):
        try: p=json.load(open(h))['points']; px=p[-1]['close'] if p else None
        except: pass
        break
    mc=sh*px if sh and px else None
    rows.append(dict(ex=ex,t=t,name=r.get('name'),level=r['level'],status=r['status'],hard=r['hardReasons'],
      sev={k:(s['severity'] if s['available'] else None) for k,s in sig.items()},
      val={k:s['value'] for k,s in sig.items() if s['available']},
      mc=mc,sector=sec,fin=uni.get((ex,t),{}).get('raw_provider_fields',{}).get('nasdaq_financial_status'),
      equity=f.get('total_equity'),assets=f.get('total_assets')))
json.dump(rows,open('us_rows.json','w'))
print(len(rows),sum(1 for r in rows if r['mc']),sum(1 for r in rows if r['sector']))
