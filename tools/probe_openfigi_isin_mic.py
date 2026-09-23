from __future__ import annotations

import json
import time
import requests

URL = "https://api.openfigi.com/v3/mapping"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "BIAP-Global-OpenFIGI-Probe/1.0"}

CASES = [
    ("Ferrari Milan", "NL0011585146", "MTAA"),
    ("Eni Milan", "IT0003132476", "MTAA"),
    ("LVMH Paris", "FR0000121014", "XPAR"),
    ("TotalEnergies Paris", "FR0000120271", "XPAR"),
    ("Apple Milan should not be native", "US0378331005", "MTAA"),
    ("Apple primary-ish Nasdaq", "US0378331005", "XNAS"),
]


def call(jobs):
    r = requests.post(URL, headers=HEADERS, json=jobs, timeout=45)
    print("STATUS", r.status_code, "RATE", {k: v for k, v in r.headers.items() if k.lower().startswith("ratelimit")})
    r.raise_for_status()
    return r.json()


def main():
    out = {}
    # Unauthenticated OpenFIGI allows small batches; use five then one.
    for start in range(0, len(CASES), 5):
        batch = CASES[start:start+5]
        jobs = [{"idType": "ID_ISIN", "idValue": isin, "micCode": mic, "marketSecDes": "Equity"} for _, isin, mic in batch]
        response = call(jobs)
        for (label, isin, mic), result in zip(batch, response):
            out[label] = {"isin": isin, "mic": mic, "result": result}
        if start + 5 < len(CASES):
            time.sleep(3)
    print(json.dumps(out, indent=2, ensure_ascii=False))

    def tickers(label):
        data = out[label].get("result", {}).get("data") or []
        return {str(x.get("ticker") or "").upper() for x in data}
    assert "RACE" in tickers("Ferrari Milan"), out["Ferrari Milan"]
    assert "ENI" in tickers("Eni Milan"), out["Eni Milan"]
    assert "MC" in tickers("LVMH Paris"), out["LVMH Paris"]
    assert "TTE" in tickers("TotalEnergies Paris"), out["TotalEnergies Paris"]


if __name__ == "__main__":
    main()
