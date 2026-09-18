"""Warm a broader daily EOD market-history baseline for BIAP Global.

This list is a data-coverage set, not an investment recommendation. It expands
server-side price/history snapshots for large/liquid operating companies across
US, Europe, Türkiye and Brazil so cross-market scans are less dependent on first-user
traffic. Official fundamentals remain a separate source layer and Evidence Agent
still decides whether any company is recommendation-eligible.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

from .runtime import build_registry


_TARGETS: dict[tuple[str, str], tuple[str, ...]] = {
    ("US", "NASDAQ"): (
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","AVGO","COST","NFLX","AMD",
        "QCOM","CSCO","AMAT","INTC","TXN","ADBE","PEP","TMUS","INTU","BKNG","WMT",
    ),
    ("US", "NYSE"): (
        "JPM","XOM","JNJ","V","MA","PG","BAC","KO","CVX",
        "CAT","GE","IBM","HD","MRK","ABBV","CRM","ORCL","MCD","DIS",
    ),
    ("GB", "LSE"): (
        "AZN","SHEL","HSBA","ULVR","BP","LSEG","GSK","REL","BATS","RIO",
    ),
    ("DE", "XETRA"): (
        "SAP","SIE","ALV","DTE","MBG","BMW","BAS","RWE","MUV2","IFX",
    ),
    ("FR", "EURONEXT_PARIS"): (
        "MC","OR","TTE","SAN","AIR","BNP","SU","AI","CS","DG",
    ),
    ("NL", "EURONEXT_AMSTERDAM"): (
        "ASML","INGA","PHIA","ADYEN","PRX","HEIA","UNA","WKL",
    ),
    ("ES", "BME_MADRID"): (
        "SAN","ITX","IBE","BBVA","TEF","REP","FER","CABK",
    ),
    ("IT", "EURONEXT_MILAN"): (
        "ENI","ENEL","ISP","UCG","STLAM","G","SRG","TRN",
    ),
    ("SE", "NASDAQ_STOCKHOLM"): (
        "VOLV.B","ERIC.B","ATCO.A","ATCO.B","INVE.B","SEB.A","SWED.A","HM.B","SAND","ASSA.B",
    ),
    ("NO", "EURONEXT_OSLO"): (
        "EQNR","DNB","AKER","MOWI","TEL","NHY","YAR","ORK","KOG","STB",
    ),
    ("DK", "NASDAQ_COPENHAGEN"): (
        "NOVO.B","MAERSK.B","DSV","CARL.B","VWS","COLO.B","ORSTED",
    ),
    ("FI", "NASDAQ_HELSINKI"): (
        "NOKIA","KNEBV","SAMPO","NESTE","UPM","FORTUM","WRT1V",
    ),
    ("BE", "EURONEXT_BRUSSELS"): (
        "ABI","KBC","UCB","SOLB","GBLB",
    ),
    ("IE", "EURONEXT_DUBLIN"): (
        "BIRG","RYA",
    ),
    ("PT", "EURONEXT_LISBON"): (
        "EDP","GALP","JMT","BCP",
    ),
    ("IS", "NASDAQ_ICELAND"): (
        "ARION","ISB","ICEAIR",
    ),
    ("TR", "BIST"): (
        "AKBNK","GARAN","THYAO","ASELS","KCHOL","BIMAS","TUPRS","FROTO","SAHOL","EREGL","ISCTR","TCELL",
    ),
    ("BR", "B3"): (
        "PETR3","VALE3","ITUB3","BBDC3","BBAS3","WEGE3","ABEV3","B3SA3","RENT3","SUZB3",
    ),
}


def _market_rows(registry, country: str, exchange: str):
    provider = registry.universe(country, exchange)
    rows = list(provider.list_instruments(country=country, exchange=exchange))
    return {row.ticker.strip().upper(): row for row in rows}


def main() -> int:
    registry = build_registry()
    workers = max(1, min(int(os.environ.get("BIAP_GLOBAL_MARKET_WARM_WORKERS", "8")), 12))
    summary = {
        "markets": 0,
        "targets": 0,
        "resolved": 0,
        "marketOk": 0,
        "misses": [],
        "failures": [],
    }

    jobs: list[tuple[str, str, object]] = []
    for (country, exchange), tickers in _TARGETS.items():
        summary["markets"] += 1
        summary["targets"] += len(tickers)
        try:
            by_ticker = _market_rows(registry, country, exchange)
        except Exception as exc:
            summary["failures"].append(f"{country}/{exchange}:universe:{type(exc).__name__}")
            continue
        for ticker in tickers:
            seed = by_ticker.get(ticker.upper())
            if seed is None:
                summary["misses"].append(f"{country}/{exchange}/{ticker}")
                continue
            summary["resolved"] += 1
            jobs.append((country, exchange, seed))

    def warm(job):
        country, exchange, seed = job
        registry.market(country, exchange).enrich_market(seed)
        return f"{country}/{exchange}/{seed.ticker}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(warm, job): job for job in jobs}
        for future in as_completed(future_map):
            country, exchange, seed = future_map[future]
            try:
                future.result()
                summary["marketOk"] += 1
            except Exception as exc:
                summary["failures"].append(
                    f"{country}/{exchange}/{seed.ticker}:market:{type(exc).__name__}:{str(exc)[:120]}"
                )

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
