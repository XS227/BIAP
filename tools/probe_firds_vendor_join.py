from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
import xml.etree.ElementTree as ET

import requests

from global_markets.universe import TwelveDataUniverseProvider

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
HEADERS = {"User-Agent": "BIAP-Global-FIRDS-join-probe/1.0 (+https://setai.no)"}

MARKETS = {
    "FR": {"exchange": "EURONEXT_PARIS", "native_mics": {"XPAR"}, "known": {"FR0000121014": "LVMH", "FR0000120271": "TotalEnergies"}},
    "IT": {"exchange": "EURONEXT_MILAN", "native_mics": {"MTAA"}, "known": {"NL0011585146": "Ferrari", "IT0003132476": "Eni"}},
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


def latest_files() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=20)
    params = {
        "q": "*",
        "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
        "wt": "json",
        "rows": "2000",
    }
    r = requests.get(SOLR, params=params, headers=HEADERS, timeout=45)
    r.raise_for_status()
    docs = (r.json().get("response") or {}).get("docs") or []
    rows = [
        d for d in docs
        if str(d.get("file_type") or "").upper() == "FULINS"
        and "FULINS_E_" in str(d.get("file_name") or "").upper()
    ]
    rows.sort(key=lambda d: (str(d.get("publication_date") or ""), str(d.get("file_name") or "")), reverse=True)
    latest_date = str(rows[0].get("publication_date") or "")[:10]
    return sorted([d for d in rows if str(d.get("publication_date") or "")[:10] == latest_date], key=lambda d: str(d.get("file_name") or ""))


def official_sets() -> dict[str, dict[str, dict]]:
    output = {country: {} for country in MARKETS}
    mic_to_country = {mic: country for country, cfg in MARKETS.items() for mic in cfg["native_mics"]}
    for doc in latest_files():
        response = requests.get(doc["download_link"], headers=HEADERS, timeout=120)
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
                    if not country or relevant != actual or not cfi.startswith("ES") or currency != "EUR" or not isin:
                        elem.clear()
                        continue
                    output[country][isin] = {
                        "isin": isin,
                        "name": text(general, "FullNm") or text(general, "ShrtNm"),
                        "cfi": cfi,
                        "actualVenue": actual,
                        "relevantVenue": relevant,
                    }
                    elem.clear()
    return output


def main() -> None:
    official = official_sets()
    report = {}
    for country, cfg in MARKETS.items():
        provider = TwelveDataUniverseProvider(api_key="demo", timeout=30, max_rows=20000)
        vendor_rows = list(provider.list_instruments(country=country, exchange=cfg["exchange"]))
        vendor_with_isin = [row for row in vendor_rows if row.isin]
        by_isin = {}
        for row in vendor_with_isin:
            by_isin.setdefault(row.isin, []).append(row)
        joined = []
        ambiguous = 0
        for isin, identity in official[country].items():
            matches = by_isin.get(isin, [])
            if len(matches) == 1:
                row = matches[0]
                joined.append({**identity, "ticker": row.ticker, "vendorMic": row.mic_code, "vendorName": row.name})
            elif len(matches) > 1:
                # Prefer the configured venue local row if there is exactly one.
                exact = [row for row in matches if row.mic_code in ({"XPAR"} if country == "FR" else {"XMIL", "MTAA"})]
                if len(exact) == 1:
                    row = exact[0]
                    joined.append({**identity, "ticker": row.ticker, "vendorMic": row.mic_code, "vendorName": row.name})
                else:
                    ambiguous += 1

        coverage = 0.0 if not official[country] else 100.0 * len(joined) / len(official[country])
        known = {}
        for isin, label in cfg["known"].items():
            known[label] = {
                "official": official[country].get(isin),
                "joined": next((row for row in joined if row["isin"] == isin), None),
            }
        report[country] = {
            "officialCount": len(official[country]),
            "vendorCount": len(vendor_rows),
            "vendorWithIsin": len(vendor_with_isin),
            "joinedCount": len(joined),
            "joinCoveragePct": round(coverage, 2),
            "ambiguous": ambiguous,
            "known": known,
            "sampleJoined": joined[:20],
            "vendorIsinPrefixTop": Counter((row.isin or "")[:2] for row in vendor_with_isin).most_common(15),
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
