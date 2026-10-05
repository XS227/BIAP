import json
import requests

url="https://biap.dadashi.no/global-api/global/scan"
payload={"country":"TR","exchange":"BIST","topN":5,"discoveryLimit":5000,"deepLimit":10}
r=requests.post(url,json=payload,timeout=300)
r.raise_for_status()
d=r.json()
keys=["status","rankingEligible","universeDiscovered","universeResolved","universeScreened","quotesUsable","deepAnalyzed","screeningCoveragePct","fundamentalCoveragePct","recommendationCount","screeningErrors"]
print(json.dumps({k:d.get(k) for k in keys},ensure_ascii=False,indent=2))
print("READINESS",json.dumps(d.get("dataReadiness"),ensure_ascii=False,indent=2))
for row in (d.get("deepResults") or [])[:10]:
    print("DEEP",json.dumps({
        "ticker":row.get("ticker"),
        "call":row.get("call"),
        "evidence":(row.get("evidence") or {}).get("status"),
        "reasoning":(row.get("evidence") or {}).get("reasoning"),
        "screening":row.get("screening"),
        "fundamentalsProvider":(row.get("providerDiagnostics") or {}).get("fundamentalsProvider"),
        "fundamentalsError":(row.get("providerDiagnostics") or {}).get("fundamentalsError"),
    },ensure_ascii=False))
assert d.get("rankingEligible") is True, d.get("dataReadiness")
assert float(d.get("screeningCoveragePct") or 0) >= 90
assert float(d.get("fundamentalCoveragePct") or 0) >= 70
assert (d.get("dataReadiness") or {}).get("universeSource") == "official-bist-daily-equity-universe"
