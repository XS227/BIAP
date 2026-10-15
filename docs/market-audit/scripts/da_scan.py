import json,os,re,sqlite3,zlib,collections,sys
pk='/var/lib/biap-global/cache/oam-esef/packages/'
idx={}
for f in os.listdir(pk):
    try:
        with open(pk+f) as h: head=h.read(400)
        m=re.search(r'"documentId":\s*"([^"]+)"',head)
        if m: idx[m.group(1)]=f
    except Exception: pass
print('packages indexed',len(idx),file=sys.stderr)
c=sqlite3.connect('snap/GB__LSE.sqlite3')
pat=re.compile(r'Depreciation|Amortisation|Amortization',re.I)
tagcount=collections.Counter(); n=0; unlock=0; rows=[]
for t,b in c.execute("select ticker,result from ledger where in_universe=1 and status='COMPLETE' and result is not null"):
    d=json.loads(zlib.decompress(b)); fe=d['fundamentalEvidence']; v=fe['values']
    if v.get('ebitda') is not None or v.get('operating_income') is None: continue
    doc=fe.get('officialDocumentId'); f=idx.get(doc)
    if not f: continue
    n+=1
    pkg=json.load(open(pk+f)); per=fe['reportPeriod']
    found={}
    for x in pkg['facts']:
        dm=x['dimensions']
        if set(dm)-{'concept','entity','period','unit'}: continue
        if pat.search(dm['concept']) and dm['period'].endswith(per) and dm['period'].startswith(str(int(per[:4])-1)) or (pat.search(dm['concept']) and dm['period'].endswith(per) and '/' in dm['period']):
            found[dm['concept']]=x['value']
    for k in found: tagcount[k]+=1
    if found: unlock+=1
    rows.append((t,found))
print(n,unlock); 
for k,v in tagcount.most_common(25): print(v,k)
json.dump(rows,open('da_scan.json','w'))
