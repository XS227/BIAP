"""Official exchange-disclosed share counts and market capitalisation.

Sources (public exchange pages/APIs, no authentication, polite rate):

* Nasdaq Nordic instrument summary (``api.nasdaq.com/api/nordic/instruments/
  <orderbookId>/summary``): ``Shares`` and ``Market Cap of Share Series`` per
  *share series* -- i.e. per class (SE/DK/FI/IS).
* Borsa Italiana "dati completi" page: ``Market Capitalization`` per instrument
  (IT). It carries no share count, so only a market cap is recorded.

Everything is cached with its fetch time under
``$BIAP_GLOBAL_DATA_DIR/shares/<provider>.json``. Reads never use the network.

Class handling: exchange counts are per series. ``issuer_total`` sums every
*listed* series of one issuer (same base ticker, e.g. ``VOLV.A`` + ``VOLV.B``).
A class-suffixed ticker with only one listed series may have unlisted classes,
so its total is only used when it can be validated against net income / EPS.
The consumer (``apply_to_company``) records source, as-of date, class and the
validation outcome in ``raw_provider_fields['exchange_share_count']``.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from .models import GlobalCompany, SourceEvidence
from .source_cache import write_bulk_text

NASDAQ_NORDIC_PROVIDER = "official-nasdaq-nordic-instrument-summary"
BORSA_ITALIANA_PROVIDER = "official-borsa-italiana-instrument-page"
LSE_PROVIDER = "official-lse-price-explorer-market-cap"
AMF_PROVIDER = "official-amf-voting-rights-notice"
BRREG_PROVIDER = "official-brreg-enhetsregisteret-share-capital"
_SUMMARY_URL = "https://api.nasdaq.com/api/nordic/instruments/{orderbook}/summary"
_BI_URL = "https://www.borsaitaliana.it/borsa/azioni/dati-completi.html?isin={isin}&mic={mic}&lang=en"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
MAX_AGE_DAYS = 120
# Share count vs net income / EPS (weighted average shares) must agree this
# tightly before an issuer-level total is trusted; buybacks explain a few %.
VALIDATION_BAND = (0.85, 1.15)


def _number(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text or text in {"-", "N/A"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number == number and number > 0 else None


def _number_signed(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _root() -> Path:
    return Path(os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global").expanduser() / "shares"


def _store_path(provider: str, country: str, exchange: str) -> Path:
    override = os.environ.get("BIAP_GLOBAL_SHARES_DIR")
    base = Path(override).expanduser() if override else _root()
    return base / f"{provider}__{country.upper()}__{exchange.upper()}.json"


def parse_nasdaq_summary(payload: dict) -> Optional[dict]:
    data = ((payload or {}).get("data") or {}).get("summaryData") or {}
    shares = _number((data.get("shares") or {}).get("value"))
    cap = _number((data.get("marketCap") or {}).get("value"))
    isin = str((data.get("isin") or {}).get("value") or "").strip().upper()
    if shares is None or len(isin) != 12:
        return None
    return {"isin": isin, "shares": shares, "market_cap": cap}


def parse_borsa_italiana(html: str) -> Optional[float]:
    text = re.sub(r"<[^>]+>", "\n", html)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines[:-1]):
        if line.lower() == "market capitalization":
            return _number(lines[i + 1])
    return None


def _write_store(provider: str, country: str, exchange: str, entries: dict, meta: dict) -> Path:
    path = _store_path(provider, country, exchange)
    payload = {"schemaVersion": 1, "provider": provider, "fetchedAt": datetime.now(timezone.utc).isoformat(),
               **meta, "entries": entries}
    write_bulk_text(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return path


def refresh_nasdaq_nordic(instruments: Iterable[dict], country: str, exchange: str, *, delay: float = 0.25, session=None,
                          sleep: Callable[[float], None] = time.sleep) -> dict:
    """``instruments``: universe rows (dicts) with ticker/isin/currency/raw_provider_fields."""
    import requests
    http = session or requests.Session()
    entries: dict = {}
    failed: list[str] = []
    for row in instruments:
        raw = row.get("raw_provider_fields") or {}
        orderbook = str(raw.get("nasdaq_orderbook_id") or "").strip()
        isin = str(row.get("isin") or "").upper()
        if not orderbook or not isin:
            continue
        try:
            response = http.get(_SUMMARY_URL.format(orderbook=orderbook), params={"assetClass": "SHARES", "lang": "en"},
                                headers={"User-Agent": _UA, "Accept": "application/json"}, timeout=20)
            response.raise_for_status()
            parsed = parse_nasdaq_summary(response.json())
        except Exception:  # noqa: BLE001 - recorded, never fabricated
            parsed = None
        if not parsed or parsed["isin"] != isin:
            failed.append(str(row.get("ticker")))
        else:
            entries[f"{row['country']}:{row['exchange']}:{row['ticker']}"] = {
                **parsed, "ticker": row["ticker"], "country": row["country"], "exchange": row["exchange"],
                "currency": row.get("currency"), "orderbook_id": orderbook,
                "source_url": _SUMMARY_URL.format(orderbook=orderbook),
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        sleep(delay)
    return {"stored": len(entries), "failed": failed, "path": str(_write_store(NASDAQ_NORDIC_PROVIDER, country, exchange, entries, {}))}


def refresh_borsa_italiana(instruments: Iterable[dict], country: str, exchange: str, *, delay: float = 0.4, session=None,
                           sleep: Callable[[float], None] = time.sleep) -> dict:
    import requests
    http = session or requests.Session()
    entries: dict = {}
    failed: list[str] = []
    for row in instruments:
        isin = str(row.get("isin") or "").upper()
        if len(isin) != 12:
            continue
        mic = str(row.get("mic_code") or "MTAA").upper()
        try:
            response = http.get(_BI_URL.format(isin=isin, mic=mic), headers={"User-Agent": _UA}, timeout=25)
            response.raise_for_status()
            cap = parse_borsa_italiana(response.text)
        except Exception:  # noqa: BLE001
            cap = None
        if cap is None:
            failed.append(str(row.get("ticker")))
        else:
            entries[f"{row['country']}:{row['exchange']}:{row['ticker']}"] = {
                "isin": isin, "ticker": row["ticker"], "country": row["country"], "exchange": row["exchange"],
                "currency": row.get("currency") or "EUR", "shares": None, "market_cap": cap,
                "source_url": _BI_URL.format(isin=isin, mic=mic),
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        sleep(delay)
    return {"stored": len(entries), "failed": failed, "path": str(_write_store(BORSA_ITALIANA_PROVIDER, country, exchange, entries, {}))}


def refresh_amf_voting_rights(instruments: Iterable[dict], country: str, exchange: str, *, delay: float = 0.4, session=None,
                              sleep: Callable[[float], None] = time.sleep, pdf_text=None) -> dict:
    """French share counts from AMF "total voting rights and shares" notices (regulated information)."""
    import requests
    from .amf_voting_rights import fetch_latest_notice
    http = session or requests.Session()
    http.headers.setdefault("User-Agent", _UA)
    entries: dict = {}
    failed: dict[str, str] = {}
    for row in instruments:
        isin = str(row.get("isin") or "").upper()
        ticker = str(row.get("ticker"))
        if len(isin) != 12:
            failed[ticker] = "no_isin"
            continue
        try:
            found, status = fetch_latest_notice(http, isin, pdf_text=pdf_text)
        except Exception as exc:  # noqa: BLE001
            found, status = None, f"feed:{type(exc).__name__}"
        if not found:
            failed[ticker] = status
        else:
            entries[f"{country}:{exchange}:{ticker}"] = {
                "isin": isin, "ticker": ticker, "country": country, "exchange": exchange,
                "currency": row.get("currency") or "EUR", "shares": found["shares"], "market_cap": None,
                "as_of": found["as_of"], "parse_rule": found["rule"], "notice_id": found["notice_id"],
                "source_url": found["source_url"], "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        sleep(delay)
    return {"stored": len(entries), "failed": failed,
            "path": str(_write_store(AMF_PROVIDER, country, exchange, entries, {}))}


def refresh_brreg_share_capital(instruments: Iterable[dict], country: str, exchange: str, *, delay: float = 0.3, session=None,
                                sleep: Callable[[float], None] = time.sleep) -> dict:
    """Norwegian issued share counts (Enhetsregisteret), identity via GLEIF ISIN -> registered id."""
    import requests
    from .brreg_share_capital import BRREG_URL, GLEIF_URL, orgnr_from_gleif, share_capital_from_brreg
    http = session or requests.Session()
    entries: dict = {}
    failed: dict[str, str] = {}
    for row in instruments:
        isin = str(row.get("isin") or "").upper()
        ticker = str(row.get("ticker"))
        if len(isin) != 12:
            failed[ticker] = "no_isin"
            continue
        try:
            g = http.get(GLEIF_URL, params={"filter[isin]": isin, "page[size]": 20},
                         headers={"Accept": "application/vnd.api+json", "User-Agent": _UA}, timeout=25)
            g.raise_for_status()
            ident, status = orgnr_from_gleif(g.json())
            found = None
            if ident:
                b = http.get(BRREG_URL.format(orgnr=ident["orgnr"]), headers={"Accept": "application/json", "User-Agent": _UA},
                             timeout=25)
                b.raise_for_status()
                found, status = share_capital_from_brreg(b.json(), ident["orgnr"], ident["legal_name"])
        except Exception as exc:  # noqa: BLE001 - recorded, never fabricated
            found, status = None, f"fetch:{type(exc).__name__}"
        if not found:
            failed[ticker] = status
        else:
            entries[f"{country}:{exchange}:{ticker}"] = {
                "isin": isin, "ticker": ticker, "country": country, "exchange": exchange, "currency": row.get("currency"),
                "shares": found["shares"], "market_cap": None, "as_of": found["as_of"], "lei": ident["lei"],
                "orgnr": ident["orgnr"], "source_url": BRREG_URL.format(orgnr=ident["orgnr"]),
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        sleep(delay)
    return {"stored": len(entries), "failed": failed,
            "path": str(_write_store(BRREG_PROVIDER, country, exchange, entries, {}))}


def refresh_lse(country: str = "GB", exchange: str = "LSE") -> dict:
    """One request for the whole Main Market (LSE Price Explorer, official)."""
    from .lse_official import LSEOfficialClient, _valid_isin
    observed, rows, _meta = LSEOfficialClient().eligible_rows()
    entries: dict = {}
    for row in rows:
        isin = _valid_isin(row.get("isin"))
        ticker = str(row.get("tidm") or "").strip().upper()
        cap = _number(row.get("marketcapitalization"))
        if not isin or not ticker or cap is None:
            continue
        if str(row.get("currency") or "").upper() not in {"GBX", "GBP"}:
            continue  # cap currency is only verified for sterling lines
        entries[f"{country}:{exchange}:{ticker}"] = {
            "isin": isin, "ticker": ticker, "country": country, "exchange": exchange, "currency": "GBP",
            "shares": None, "market_cap": cap, "orderbook_id": None,
            "source_url": "https://www.londonstockexchange.com/live-markets/market-data-dashboard/price-explorer",
            "observed_at": f"{observed}T00:00:00+00:00",
        }
    return {"stored": len(entries), "failed": [], "path": str(_write_store(LSE_PROVIDER, country, exchange, entries, {}))}


# ---------------------------------------------------------------- consumption
_store_cache: dict[str, tuple[float, dict]] = {}


def _load(provider: str, country: str, exchange: str) -> Optional[dict]:
    path = _store_path(provider, country, exchange)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _store_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1 or not isinstance(payload.get("entries"), dict):
        return None
    _store_cache[str(path)] = (mtime, payload)
    return payload


def _base_ticker(ticker: str) -> str:
    return str(ticker).upper().split(".")[0].split("-")[0]


def _has_class_suffix(ticker: str) -> bool:
    return bool(re.search(r"[.\-][A-Z]$", str(ticker).upper()))


def lookup(company: GlobalCompany) -> Optional[dict]:
    """Return the cached exchange entry (with issuer aggregation) for a company."""
    for provider in (NASDAQ_NORDIC_PROVIDER, BORSA_ITALIANA_PROVIDER, LSE_PROVIDER, AMF_PROVIDER, BRREG_PROVIDER):
        payload = _load(provider, company.country, company.exchange)
        if not payload:
            continue
        key = f"{company.country}:{company.exchange}:{company.ticker}"
        entry = payload["entries"].get(key)
        if not entry:
            continue
        if company.isin and str(entry.get("isin") or "").upper() != company.isin.upper():
            return None  # identity mismatch: never attach a count to a different ISIN
        siblings = [
            e for k, e in payload["entries"].items()
            if e.get("country") == company.country and e.get("exchange") == company.exchange
            and _base_ticker(e.get("ticker")) == _base_ticker(company.ticker)
        ]
        shares_series = [e["shares"] for e in siblings if e.get("shares")]
        caps = [e["market_cap"] for e in siblings if e.get("market_cap")]
        shares_complete = len(shares_series) == len(siblings)
        caps_complete = len(caps) == len(siblings)
        return {
            "provider": provider, "fetched_at": payload.get("fetchedAt"), "entry": entry,
            "series": [{"ticker": e["ticker"], "isin": e.get("isin"), "shares": e.get("shares"),
                        "market_cap": e.get("market_cap")} for e in siblings],
            "issuer_total_shares": sum(shares_series) if shares_series and shares_complete else None,
            "issuer_total_market_cap": sum(caps) if caps and caps_complete else None,
            "listed_series": len(siblings),
        }
    return None


def apply_to_company(company: GlobalCompany, *, now: Optional[datetime] = None) -> GlobalCompany:
    """Fill ``shares_outstanding`` / ``market_cap`` from a validated exchange entry.

    Existing values are never overwritten. Nothing is applied when the entry is
    stale, the ISIN differs, a listed class set cannot be shown complete, or the
    issuer total contradicts net income / EPS by more than the validation band.
    """
    if company.shares_outstanding is not None and company.market_cap is not None:
        return company
    found = lookup(company)
    if not found:
        return company
    now = now or datetime.now(timezone.utc)
    observed = found["entry"].get("observed_at") or found.get("fetched_at")
    try:
        age_days = (now - datetime.fromisoformat(str(observed).replace("Z", "+00:00"))).days
    except ValueError:
        return company
    note: dict = {"provider": found["provider"], "observed_at": observed, "ticker": company.ticker,
                  "series": found["series"], "listed_series": found["listed_series"],
                  "share_class": (company.ticker.split(".")[-1] if _has_class_suffix(company.ticker) else "single"),
                  "source_url": found["entry"].get("source_url")}
    if age_days > MAX_AGE_DAYS:
        return replace(company, raw_provider_fields={**company.raw_provider_fields,
                       "exchange_share_count": {**note, "status": f"withheld:stale_{age_days}d"}})
    total_shares = found["issuer_total_shares"]
    total_cap = found["issuer_total_market_cap"]
    status = "applied"
    # EPS is per share of the parent's owners: prefer the owners' share of profit
    # when the filing tags it, else consolidated profit (minorities included).
    owners = _number_signed(company.raw_provider_fields.get("net_income_attributable_to_owners"))
    earnings = owners if owners else company.net_income
    if total_shares is not None and earnings and company.eps and float(earnings) / float(company.eps) > 0:
        implied = float(earnings) / float(company.eps)   # sign-consistent loss years validate too
        ratio = total_shares / implied
        note["validation"] = {"basis": "net_income_attributable_to_owners/eps" if owners else "net_income/eps",
                              "implied_shares": implied, "ratio": round(ratio, 4)}
        if not VALIDATION_BAND[0] <= ratio <= VALIDATION_BAND[1]:
            return replace(company, raw_provider_fields={**company.raw_provider_fields,
                           "exchange_share_count": {**note, "status": "withheld:contradicts_net_income_over_eps"}})
    elif total_shares is not None and (_has_class_suffix(company.ticker) or found["listed_series"] > 1):
        # Class-suffixed issuer, no way to prove every class is listed.
        if found["listed_series"] == 1:
            return replace(company, raw_provider_fields={**company.raw_provider_fields,
                           "exchange_share_count": {**note, "status": "withheld:single_listed_class_of_multi_class_issuer_unvalidated"}})
        note["validation"] = {"basis": "none_available", "note": "all listed series summed; unlisted classes cannot be excluded"}
        status = "applied_unvalidated"
    elif total_shares is None and total_cap is None:
        return company
    note["status"] = status
    updates: dict = {}
    if company.shares_outstanding is None and total_shares is not None:
        updates["shares_outstanding"] = total_shares
    if company.market_cap is None and total_cap is not None:
        updates["market_cap"] = total_cap
    if not updates:
        return company
    source = SourceEvidence(
        provider=found["provider"], source_type="official_exchange_share_count",
        source_id=f"{company.country}:{company.exchange}:{company.ticker}",
        source_url=found["entry"].get("source_url"), observed_at=str(observed), quality=1.0,
        notes=f"exchange-disclosed share count/market cap; status={status}; issuer total over {found['listed_series']} listed series",
    )
    return replace(company, **updates,
                   raw_provider_fields={**company.raw_provider_fields, "exchange_share_count": note,
                                        **({"exchange_market_cap": {"value": total_cap, "currency": company.currency,
                                            "provider": found["provider"], "as_of": str(observed)[:10],
                                            "basis": "sum_of_listed_series_market_cap"}} if "market_cap" in updates else {})},
                   sources=[*company.sources, source])


def main(argv: Optional[list[str]] = None) -> int:
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) not in (3, 4) or args[0] != "refresh":
        print("usage: python -m global_markets.exchange_shares refresh <COUNTRY> <EXCHANGE> [instruments.json]")
        return 2
    country, exchange = args[1].upper(), args[2].upper()
    base = Path(os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global")
    if (country, exchange) == ("GB", "LSE"):
        rows = []
    elif len(args) == 4:  # explicit list: {"companies": [{"ticker", "isin", ...}]} (audit / benchmark JSON)
        listed = json.loads(Path(args[3]).read_text(encoding="utf-8"))["companies"]
        rows = [{"ticker": c["ticker"], "isin": c.get("isin"), "country": country, "exchange": exchange,
                 "currency": (c.get("market") or {}).get("currency")} for c in listed]
    else:
        universe = json.loads((base / "universe" / country / f"{exchange}.json").read_text(encoding="utf-8"))
        rows = universe["instruments"]
    if country in {"SE", "DK", "FI", "IS"}:
        result = refresh_nasdaq_nordic(rows, country, exchange)
    elif country == "IT":
        result = refresh_borsa_italiana(rows, country, exchange)
    elif (country, exchange) == ("GB", "LSE"):
        result = refresh_lse(country, exchange)
    elif country == "FR":
        result = refresh_amf_voting_rights(rows, country, exchange)
    elif country == "NO":
        result = refresh_brreg_share_capital(rows, country, exchange)
    else:
        print(f"no official share-count source configured for {country}/{exchange}")
        return 1
    print(json.dumps({k: (v if k != "failed" or isinstance(v, dict) else v[:20]) for k, v in result.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
