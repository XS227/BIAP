import sqlite3,json,urllib.request,collections,statistics as S
c=sqlite3.connect("file:/var/lib/biap-global/analysis-ledger/DE__XETRA.sqlite3?mode=ro",uri=True)
ts=[r[0] for r in c.execute("select ticker from ledger where in_universe=1 and status='COMPLETE' and evidence_status='PASS' order by priority desc limit 120")]
out={}
for t in ts:
    try:
        req=urllib.request.Request("http://127.0.0.1:8091/global/analyze",json.dumps({"country":"DE","exchange":"XETRA","ticker":t}).encode(),{"content-type":"application/json"})
        d=json.load(urllib.request.urlopen(req,timeout=180))
    except Exception as e: out[t]={"err":str(e)};continue
    di=d.get("decisionIntegrity") or {}
    m=(d.get("decisionTable") or {}).get("metrics") or {}
    out[t]={"call":d["call"],"score":d["score"],"conf":d["confidence"],"prelim":di.get("preliminaryCall"),"gov":di.get("governanceAction"),"distress":((d.get("distress") or {}).get("status")),
      "votes":{s["agent"]:s["vote"] for s in d["signals"]},"r6m":m.get("return6mPct"),"mcap":m.get("marketCap"),"pe":m.get("pe"),"sector":(d.get("company") or {}).get("sector")}
json.dump(out,open("de_scan.json","w"),indent=0)
