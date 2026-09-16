"""BIAP Global evidence requirements and source plan.

This is operational metadata for the app/API and deployment checklist. It does
not claim that every listed official source already has a live parser. `status`
is explicit so the UI can distinguish connected evidence from planned sources.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class DataRequirement:
    key: str
    group: str
    critical: bool
    description: str


ANALYSIS_REQUIREMENTS: tuple[DataRequirement, ...] = (
    DataRequirement("identity", "instrument", True, "country, ticker, exchange/MIC plus ISIN/LEI when available"),
    DataRequirement("price", "market", True, "verified current/latest tradable price with timestamp"),
    DataRequirement("ohlcv_history", "market", True, "split-adjusted daily OHLCV history for returns, volatility and drawdown"),
    DataRequirement("corporate_actions", "market", False, "splits, dividends and symbol changes so history is not distorted"),
    DataRequirement("market_cap", "market", False, "market capitalization and shares outstanding"),
    DataRequirement("fundamentals", "filings", True, "revenue, profit, margins, assets, liabilities and equity from official/verified regulatory filings"),
    DataRequirement("cash_flow", "filings", True, "operating cash flow, capex/free cash flow and debt where applicable"),
    DataRequirement("valuation", "analysis", False, "P/E, P/B, EV/EBITDA and peer/sector comparables when valid"),
    DataRequirement("audit_and_scope", "filings", False, "audit opinion plus consolidated/standalone reporting scope when verifiable"),
    DataRequirement("material_events", "filings", False, "material disclosures, restatements, governance and corporate actions"),
    DataRequirement("fx", "portfolio", True, "verified FX conversion into investor base currency for cross-border allocation"),
    DataRequirement("market_calendar", "execution", True, "exchange timezone, trading sessions and holidays"),
    DataRequirement("broker_contract", "execution", True, "broker instrument/contract identifier, lot size and trading permission"),
    DataRequirement("costs", "execution", False, "commissions, fees and estimated spread for realistic paper/live evaluation"),
)

# connected = a verified fundamentals/evidence adapter exists, though credentials
# or authorized ingestion may still be required at deployment time.
# bridge = existing Iran production path reused read-only.
# market-ready = exchange routing exists but verified fundamentals adapter remains planned.
SOURCE_PLANS: dict[str, dict] = {
    "IR": {"market": "TSETMC", "filings": "CODAL", "status": "bridge", "notes": "Existing Iran path reused read-only."},
    "US": {"market": "licensed global feed", "filings": "SEC EDGAR/XBRL Company Facts", "status": "connected", "notes": "SEC adapter implemented; real User-Agent required."},
    "CA": {"market": "global market feed", "filings": "SEDAR+", "status": "market-ready"},
    "GB": {"market": "LSE / licensed global feed", "filings": "UKSEF/ESEF + Companies House corroboration", "status": "connected", "notes": "ESEF fundamentals adapter plus Companies House official metadata client."},
    "SE": {"market": "Nasdaq Nordic / global market feed", "filings": "ESEF xBRL + issuer/Nasdaq corroboration", "status": "connected"},
    "NO": {"market": "Euronext Oslo / global market feed", "filings": "ESEF xBRL + issuer/Euronext corroboration", "status": "connected"},
    "DK": {"market": "Nasdaq Nordic / global market feed", "filings": "ESEF xBRL + issuer disclosures", "status": "connected"},
    "FI": {"market": "Nasdaq Nordic / global market feed", "filings": "ESEF xBRL + issuer disclosures", "status": "connected"},
    "IS": {"market": "Nasdaq Iceland / global market feed", "filings": "ESEF xBRL where filed + issuer disclosures", "status": "connected"},
    "NL": {"market": "Euronext Amsterdam / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "FR": {"market": "Euronext Paris / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "BE": {"market": "Euronext Brussels / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "IE": {"market": "Euronext Dublin / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "PT": {"market": "Euronext Lisbon / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "IT": {"market": "Euronext Milan / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "DE": {"market": "Xetra/Frankfurt / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "ES": {"market": "BME / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "CH": {"market": "SIX / global market feed", "filings": "SIX + issuer reports", "status": "market-ready"},
    "AU": {"market": "ASX / licensed global feed", "filings": "verified ASX/issuer filing drop", "status": "connected", "notes": "Requires authorized/licensed ingestion; unverified local records are rejected."},
    "NZ": {"market": "NZX / global market feed", "filings": "NZX issuer disclosures", "status": "market-ready"},
    "JP": {"market": "Tokyo Stock Exchange / global market feed", "filings": "FSA EDINET API v2", "status": "connected", "notes": "EDINET index/cache/parser implemented; API key required and daily server sync supported."},
    "KR": {"market": "Korea Exchange / global market feed", "filings": "FSS OpenDART", "status": "connected", "notes": "OpenDART annual statement adapter implemented; API key required."},
    "HK": {"market": "HKEX / global market feed", "filings": "HKEXnews", "status": "market-ready"},
    "SG": {"market": "SGX / global market feed", "filings": "SGX issuer announcements", "status": "market-ready"},
    "IN": {"market": "NSE/BSE / global market feed", "filings": "NSE/BSE corporate filings", "status": "market-ready"},
    "SA": {"market": "Saudi Exchange / global market feed", "filings": "Saudi Exchange disclosures", "status": "market-ready"},
    "AE": {"market": "ADX/DFM / global market feed", "filings": "ADX/DFM disclosures", "status": "market-ready"},
    "TR": {"market": "Borsa Istanbul / global market feed", "filings": "KAP Public Disclosure Platform", "status": "market-ready"},
    "ZA": {"market": "JSE / global market feed", "filings": "JSE SENS + issuer reports", "status": "market-ready"},
    "BR": {"market": "B3 / global market feed", "filings": "CVM open data + issuer filings", "status": "market-ready"},
}


def requirements_payload() -> list[dict]:
    return [
        {"key": item.key, "group": item.group, "critical": item.critical, "description": item.description}
        for item in ANALYSIS_REQUIREMENTS
    ]
