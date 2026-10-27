"""BHP/HAUTO/WWI regression in-process against an isolated data copy. usage: regress10.py LABEL"""
import json, os, sys, time
from datetime import datetime, timezone
V="/home/ubuntu/biap-validation-20261016"; D=V+"/data-u9"; R="/home/ubuntu/biap-global/BIAP/analysis"
os.environ.update(BIAP_GLOBAL_DATA_DIR=D, BIAP_GLOBAL_US_ISIN_RESOLVE="1", BIAP_GLOBAL_ONLINE_FIRST="1")
sys.path.insert(0,R)
from fastapi.testclient import TestClient
from global_markets.cached_market import PersistentMarketProvider as P
def _live(self, company):
    time.sleep(0.25); e=self.upstream.enrich_market(company)
    e.raw_provider_fields.update({"market_cache":"live","market_cache_age_hours":0.0}); return e   # harness: live quote, nothing written
P.refresh=_live
import global_api_server
c=TestClient(global_api_server.app)
NAMES=[("GB","LSE","BHP"),("NO","EURONEXT_OSLO","HAUTO"),("NO","EURONEXT_OSLO","WWI")]
label=sys.argv[1]; out={"label":label,"at":datetime.now(timezone.utc).isoformat(),"names":{}}
for co,ex,t in NAMES:
    q=c.get(f"/global/instruments/{co}/{ex}",params={"q":t,"limit":5}).json()
    rows=q.get("instruments") or q.get("items") or q.get("results") or []
    row=next(x for x in rows if x["ticker"].upper()==t)
    body={k:row[k] for k in ("country","exchange","ticker","name","currency","isin","lei") if row.get(k)}
    r=c.post("/global/analyze",json=body).json()
    raw=(r.get("rawProviderFields") or {})
    out["names"][t]={"call":r.get("call"),"state":(r.get("opportunity") or {}).get("state"),"confidence":r.get("confidence"),
      "evidence":(r.get("evidence") or {}).get("status"),"governance":(r.get("governance") or {}).get("status") or (r.get("governance") or {}).get("decision"),
      "reasons":(r.get("opportunity") or {}).get("limitingFactors"),"cause":(r.get("opportunity") or {}).get("primaryCause")}
    print(label,t,out["names"][t],flush=True)
json.dump(out,open(f"{V}/out10/{label}.json","w"),indent=1)
