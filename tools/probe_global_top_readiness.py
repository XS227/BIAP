import json
import requests

URL = "https://biap.dadashi.no/global-api/global/scan-global"
payload = {"topN": 10, "maxAgeHours": 36}
response = requests.post(URL, json=payload, timeout=60)
response.raise_for_status()
data = response.json()

summary = {
    "status": data.get("status"),
    "marketsScanned": data.get("marketsScanned"),
    "marketsEligible": data.get("marketsEligible"),
    "marketsExcluded": data.get("marketsExcluded"),
    "eligibleEquities": data.get("eligibleEquities"),
    "screenedEquities": data.get("screenedEquities"),
    "globalCoveragePct": data.get("globalCoveragePct"),
    "connectedCoveragePct": data.get("connectedCoveragePct"),
    "recommendationCount": data.get("recommendationCount"),
}
print("GLOBAL", json.dumps(summary, ensure_ascii=False, sort_keys=True))
for row in data.get("markets") or []:
    ready = row.get("dataReadiness") or {}
    print("MARKET", json.dumps({
        "country": row.get("country"),
        "exchange": row.get("exchange"),
        "status": row.get("status"),
        "rankingEligible": row.get("rankingEligible"),
        "eligibleEquities": row.get("eligibleEquities"),
        "screenedEquities": row.get("screenedEquities"),
        "screeningCoveragePct": row.get("screeningCoveragePct"),
        "fundamentalCoveragePct": row.get("fundamentalCoveragePct"),
        "readinessStatus": ready.get("status"),
        "universeSource": ready.get("universeSource"),
        "marketSource": ready.get("marketSource"),
        "reasons": ready.get("reasons"),
        "cache": row.get("cache"),
        "error": row.get("error"),
    }, ensure_ascii=False, sort_keys=True))
