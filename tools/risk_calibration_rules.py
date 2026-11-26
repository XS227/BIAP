import json,collections
R=json.load(open('us_rows.json'))
pos=[r for r in R if r['fin'] in('D','E','H')]; neg=[r for r in R if r['fin']=='N']
def auc(key,sign=1):
    p=[sign*r['val'][key] for r in pos if key in r['val']]; n=[sign*r['val'][key] for r in neg if key in r['val']]
    if not p or not n: return None,len(p),len(n)
    import bisect; ns=sorted(n); s=0
    for x in p: s+=bisect.bisect_left(ns,x)+0.5*(bisect.bisect_right(ns,x)-bisect.bisect_left(ns,x))
    return round(s/(len(p)*len(n)),3),len(p),len(n)
print('AUC vs NASDAQ deficient/delinquent proxy (0.5 = no signal)')
for k,sg in (('ohlson',1),('zmijewski',1),('altman',-1),('interest_coverage',-1),('volatility',1)): print(' ',k,auc(k,sg))
# neg equity
def rate(rows,f): return round(100*sum(1 for r in rows if f(r))/max(1,len(rows)),1)
print('negative equity rate  pos',rate(pos,lambda r:r['hard']),' neg',rate(neg,lambda r:r['hard']))
print('going concern count in US', sum(1 for r in R if any('going' in h for h in r['hard'])))
# candidate rules -> level
def S(r,k): return r['sev'].get(k) or 0
def val(r,k): return r['val'].get(k)
def nsev(r,ohl=0.5): 
    n=0
    if (val(r,'ohlson') or 0)>=ohl: n+=1
    n+= S(r,'zmijewski')==2; n+= S(r,'altman')==2; n+= S(r,'interest_coverage')==2
    return n
def anyel(r,oe=0.038): return (val(r,'ohlson') or 0)>=oe or any(S(r,k)>=1 for k in('zmijewski','altman','interest_coverage','volatility'))
def cur(r): return r['level']
def A(r): # neg equity no longer automatic; going concern only automatic
    if not r['level']: return None
    if any('going' in h for h in r['hard']): return 'CRITICAL'
    n=nsev(r)
    return 'CRITICAL' if n>=3 else 'HIGH' if n>=2 else 'MEDIUM' if (n>=1 or anyel(r)) else 'LOW'
def B(r): # like A but vol and Ohlson-elevated never reach HIGH; severe solvency pair needed; ICR severe single = MEDIUM
    if not r['level']: return None
    if any('going' in h for h in r['hard']): return 'CRITICAL'
    n=nsev(r)
    return 'CRITICAL' if n>=3 else 'HIGH' if n>=2 else 'MEDIUM' if anyel(r) or n>=1 else 'LOW'
def C(r): # needs corroboration: HIGH = >=2 severe AND (neg equity or ICR/Altman distress); CRITICAL = >=3 severe AND neg equity
    if not r['level']: return None
    if any('going' in h for h in r['hard']): return 'CRITICAL'
    n=nsev(r); ne=bool(r['hard'])
    return 'CRITICAL' if n>=3 and ne else 'HIGH' if n>=3 or (n>=2 and ne) else 'MEDIUM' if n>=1 or anyel(r) else 'LOW'
def D(r): # require 3 of 4 severe for HIGH, 4 of 4 + negative equity for CRITICAL
    if not r['level']: return None
    if any('going' in h for h in r['hard']): return 'CRITICAL'
    n=nsev(r); ne=bool(r['hard'])
    return 'CRITICAL' if n>=4 and ne else 'HIGH' if n>=3 else 'MEDIUM' if n>=1 or anyel(r) else 'LOW'
for name,f in (('current',cur),('A: severe-count (neg equity not automatic)',A),('C: HIGH=3 severe or 2+negEq; CRIT=3 severe+negEq',C),('D: HIGH=3 severe; CRIT=4 severe+negEq',D)):
    dist=collections.Counter(f(r) for r in R if r['level'])
    out=[name,dict(dist)]
    for lab,thr in(('HIGH+',('HIGH','CRITICAL')),('CRIT',('CRITICAL',))):
        pr=rate([r for r in pos if r['level']],lambda r:f(r) in thr); nr=rate([r for r in neg if r['level']],lambda r:f(r) in thr)
        tot=sum(1 for r in R if r['level'] and f(r) in thr); tp=sum(1 for r in pos if r['level'] and f(r) in thr)
        out.append(f"{lab}: share flagged proxy-distressed {pr}% vs normal {nr}% (lift {round(pr/max(nr,0.1),2)}), flagged {tot} ({round(100*tot/sum(dist.values()),1)}%), precision vs proxy {round(100*tp/max(1,tot),1)}%")
    print('\n'.join(map(str,out)),'\n')

print('--- cap-controlled (micro-cap <300M only, proxy D/E/H vs N) ---')
def band(mc): return 'unknown' if not mc else '<300M' if mc<3e8 else '300M-2B' if mc<2e9 else '2-10B' if mc<1e10 else '>10B'
for name,f in (('current',cur),('C',C),('D',D)):
    for b in ('<300M','300M-2B'):
        p=[r for r in pos if r['level'] and band(r['mc'])==b]; n=[r for r in neg if r['level'] and band(r['mc'])==b]
        print(name,b,'proxy n',len(p),'normal n',len(n),'HIGH+ flagged',rate(p,lambda r:f(r) in('HIGH','CRITICAL')),'% vs',rate(n,lambda r:f(r) in('HIGH','CRITICAL')),'%')
print('--- distribution by cap band under D (US with level) ---')
for name,f in (('current',cur),('D',D)):
    for b in ('<300M','300M-2B','2-10B','>10B','unknown'):
        rr=[r for r in R if r['level'] and band(r['mc'])==b]; c=collections.Counter(f(r) for r in rr); print(name,b,len(rr),dict(c))
