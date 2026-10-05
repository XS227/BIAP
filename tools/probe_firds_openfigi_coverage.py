from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import io
import json
import os
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
FIRDS_HEADERS = {"User-Agent": "BIAP-Global-FIRDS-OpenFIGI-Coverage/1.0 (+https://setai.no)"}
FIGI_URL = "https://api.openfigi.com/v3/mapping"
FIGI_HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "BIAP-Global-OpenFIGI-Coverage/1.0"}
if os.environ.get("OPENFIGI_API_KEY"):
    FIGI_HEADERS["X-OPENFIGI-APIKEY"] = os.environ["OPENFIGI_API_KEY"].strip()

MARKETS = {
    "FR": {"mic": "XPAR", "known": {"FR0000121014": "MC", "FR0000120271": "TTE"}},
    "IT": {"mic": "MTAA", "known": {"NL0011585146": "RACE", "IT0003132476": "ENI"}},
}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(parent: ET.Element | None, name: str):
    if parent is None:
        return None
    for node in list(parent):
        if local(node.tag) == name:
            return node
    return None


def text(parent: ET.Element | None, name: str) -> str | None:
    node = child(parent, name)
    value = (node.text or "").strip() if node is not None else ""
    return value or None


def latest_files() -> tuple[str, list[dict]]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=20)
    params = {
        "q": "*",
        "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
        "wt": "json",
        "rows": "2000",
    }
    response = requests.get(SOLR, params=params, headers=FIRDS_HEADERS, timeout=45)
    response.raise_for_status()
    docs = (response.json().get("response") or {}).get("docs") or []
    rows = [
        d for d in docs
        if str(d.get("file_type") or "").upper() == "FULINS"
        and "FULINS_E_" in str(d.get("file_name") or "").upper()
    ]
    rows.sort(key=lambda d: (str(d.get("publication_date") or ""), str(d.get("file_name") or "")), reverse=True)
    if not rows:
        raise RuntimeError("No recent FULINS_E files")
    latest_date = str(rows[0].get("publication_date") or "")[:10]
    return latest_date, sorted(
        [d for d in rows if str(d.get("publication_date") or "")[:10] == latest_date],
        key=lambda d: str(d.get("file_name") or ""),
    )


def official_sets() -> tuple[str, dict[str, dict[str, dict]]]:
    publication_date, files = latest_files()
    out = {country: {} for country in MARKETS}
    mic_to_country = {cfg["mic"]: country for country, cfg in MARKETS.items()}
    for doc in files:
        response = requests.get(doc["download_link"], headers=FIRDS_HEADERS, timeout=120)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            xml_name = next(name for name in zf.namelist() if name.lower().endswith(".xml"))
            with zf.open(xml_name) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if local(elem.tag) != "RefData":
                        continue
                    general = child(elem, "FinInstrmGnlAttrbts")
                    venue = child(elem, "TradgVnRltdAttrbts")
                    tech = child(elem, "TechAttrbts")
                    isin = text(general, "Id")
                    cfi = text(general, "ClssfctnTp") or ""
                    currency = text(general, "NtnlCcy")
                    actual = text(venue, "Id")
                    relevant = text(tech, "RlvntTradgVn")
                    country = mic_to_country.get(actual or "")
                    if country and actual == relevant and cfi.startswith("ES") and currency == "EUR" and isin:
                        out[country][isin] = {
                            "isin": isin,
                            "name": text(general, "FullNm") or text(general, "ShrtNm") or isin,
                            "cfi": cfi,
                            "mic": actual,
                            "issuerLei": text(elem, "Issr"),
                        }
                    elem.clear()
    return publication_date, out


def map_batch(session: requests.Session, jobs: list[dict]) -> list[dict]:
    for attempt in range(8):
        response = session.post(FIGI_URL, headers=FIGI_HEADERS, json=jobs, timeout=45)
        if response.status_code == 429:
            reset = int(float(response.headers.get("ratelimit-reset") or 3))
            time.sleep(max(2, min(reset + 1, 65)))
            continue
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, list) or len(body) != len(jobs):
            raise RuntimeError("Unexpected OpenFIGI mapping payload")
        return body
    raise RuntimeError("OpenFIGI rate limit did not recover")


def resolve_all(official: dict[str, dict[str, dict]]) -> dict[str, dict]:
    session = requests.Session()
    report = {}
    # Unauthenticated documented limit is deliberately respected conservatively:
    # 5 jobs/request and one request every ~2.6 seconds.
    keyed = []
    for country, identities in official.items():
        for isin, identity in sorted(identities.items()):
            keyed.append((country, isin, identity))

    resolved: dict[tuple[str, str], dict] = {}
    failures: dict[tuple[str, str], str] = {}
    ambiguous: dict[tuple[str, str], list[str]] = {}
    batch_size = 5 if "X-OPENFIGI-APIKEY" not in FIGI_HEADERS else 100
    request_pause = 2.6 if "X-OPENFIGI-APIKEY" not in FIGI_HEADERS else 0.3

    for start in range(0, len(keyed), batch_size):
        batch = keyed[start:start + batch_size]
        jobs = [
            {
                "idType": "ID_ISIN",
                "idValue": isin,
                "micCode": identity["mic"],
                "marketSecDes": "Equity",
            }
            for _, isin, identity in batch
        ]
        results = map_batch(session, jobs)
        for (country, isin, identity), result in zip(batch, results):
            data = result.get("data") if isinstance(result, dict) else None
            rows = [row for row in (data or []) if isinstance(row, dict) and str(row.get("securityType2") or "").lower() in {"common stock", "equity"}]
            tickers = sorted({str(row.get("ticker") or "").strip().upper() for row in rows if str(row.get("ticker") or "").strip()})
            if len(tickers) == 1:
                ticker = tickers[0]
                chosen = next(row for row in rows if str(row.get("ticker") or "").strip().upper() == ticker)
                resolved[(country, isin)] = {
                    "ticker": ticker,
                    "figi": chosen.get("figi"),
                    "exchCode": chosen.get("exchCode"),
                    "name": chosen.get("name"),
                }
            elif len(tickers) > 1:
                ambiguous[(country, isin)] = tickers
            else:
                failures[(country, isin)] = str((result or {}).get("warning") or (result or {}).get("error") or "no common-stock ticker")
        if start + batch_size < len(keyed):
            time.sleep(request_pause)

    for country, identities in official.items():
        mapped = {isin: resolved[(country, isin)] for isin in identities if (country, isin) in resolved}
        missing = {isin: failures.get((country, isin), "ambiguous") for isin in identities if isin not in mapped}
        amb = {isin: ambiguous[(country, isin)] for isin in identities if (country, isin) in ambiguous}
        coverage = 0.0 if not identities else 100.0 * len(mapped) / len(identities)
        report[country] = {
            "officialCount": len(identities),
            "mappedCount": len(mapped),
            "coveragePct": round(coverage, 2),
            "missingCount": len(missing),
            "ambiguousCount": len(amb),
            "known": {
                isin: {"expectedTicker": expected, "mapping": mapped.get(isin), "missing": missing.get(isin)}
                for isin, expected in MARKETS[country]["known"].items()
            },
            "missingSample": list(missing.items())[:25],
            "ambiguousSample": list(amb.items())[:25],
            "mappedSample": list(mapped.items())[:20],
        }
    return report


def main() -> None:
    publication_date, official = official_sets()
    report = resolve_all(official)
    print(json.dumps({"firdsPublicationDate": publication_date, "markets": report}, indent=2, ensure_ascii=False))
    for country, cfg in report.items():
        for isin, known in cfg["known"].items():
            mapping = known.get("mapping") or {}
            assert mapping.get("ticker") == known["expectedTicker"], (country, isin, known)


if __name__ == "__main__":
    main()
