import json
import requests

URL="https://biap.dadashi.no/global-api/global/scan"
for exchange in ("NASDAQ","NYSE"):
    r=requests.post(URL,json={"country":"US","exchange":exchange,"topN":5,"discoveryLimit":5000,"deepLimit":10},timeout=300)
    r.raise_for_status()
    d=r.json()
    print("MARKET",exchange,json.dumps({
        "status":d.get("status"),
        "rankingEligible":d.get("rankingEligible"),
        "universeDiscovered":d.get("universeDiscovered"),
        "universeResolved":d.get("universeResolved"),
        "universeScreened":d.get("universeScreened"),
        "quotesUsable":d.get("quotesUsable"),
        "deepAnalyzed":d.get("deepAnalyzed"),
        "screeningCoveragePct":d.get("screeningCoveragePct"),
        "fundamentalCoveragePct":d.get("fundamentalCoveragePct"),
        "recommendationCount":d.get("recommendationCount"),
        "screeningErrors":d.get("screeningErrors"),
        "readiness":d.get("dataReadiness"),
    },ensure_ascii=False,indent=2))
    for row in (d.get("deepResults") or [])[:10]:
        print("DEEP",exchange,json.dumps({
            "ticker":row.get("ticker"),
            "call":row.get("call"),
            "evidence":(row.get("evidence") or {}).get("status"),
            "reasoning":(row.get("evidence") or {}).get("reasoning"),
            "fundamentalsProvider":(row.get("providerDiagnostics") or {}).get("fundamentalsProvider"),
            "fundamentalsError":(row.get("providerDiagnostics") or {}).get("fundamentalsError"),
        },ensure_ascii=False))
    assert (d.get("dataReadiness") or {}).get("universeSource") == "official-nasdaq-trader-us-equity-directory"
    assert float(d.get("screeningCoveragePct") or 0) >= 90
    assert float(d.get("fundamentalCoveragePct") or 0) >= 70
    assert d.get("rankingEligible") is True, d.get("dataReadiness")
