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
# partial = a strict official adapter exists only for an explicit issuer allow-list.
SOURCE_PLANS: dict[str, dict] = {
    "IR": {"market": "TSETMC", "filings": "CODAL", "status": "bridge", "notes": "Existing Iran path reused read-only."},
    "US": {"market": "licensed global feed", "filings": "SEC EDGAR/XBRL Company Facts", "status": "connected", "notes": "SEC adapter implemented; descriptive User-Agent is used when no deployment-specific contact is configured."},
    "CA": {"market": "global market feed", "filings": "SEDAR+", "status": "market-ready", "notes": "Public filings are available, but no stable machine-readable official financial-statement adapter is connected yet."},
    "GB": {"market": "LSE / licensed global feed", "filings": "UKSEF/ESEF + Companies House corroboration", "status": "connected", "notes": "ESEF fundamentals are connected. Companies House legal-entity corroboration is automatically added when BIAP_COMPANIES_HOUSE_API_KEY is configured."},
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
    "DE": {"market": "Xetra/Frankfurt / global market feed", "filings": "ESEF xBRL + SEC 20-F IFRS fallback + issuer/OAM filings", "status": "connected", "notes": "ESEF is primary. For an exact issuer identity that also files annual IFRS 20-F data with the SEC, BIAP can use verified SEC CompanyFacts as a second official source. Issuers without either machine-readable source remain explicitly blocked rather than being upgraded from vendor metrics."},
    "ES": {"market": "BME / global market feed", "filings": "ESEF xBRL + issuer/OAM filings", "status": "connected"},
    "CH": {"market": "SIX / global market feed", "filings": "SIX + issuer reports", "status": "market-ready"},
    "AU": {"market": "ASX / licensed global feed", "filings": "verified ASX/issuer filing drop", "status": "connected", "notes": "Requires authorized/licensed ingestion; unverified local records are rejected."},
    "NZ": {"market": "NZX / global market feed", "filings": "NZX issuer disclosures", "status": "market-ready"},
    "JP": {"market": "Tokyo Stock Exchange / global market feed", "filings": "FSA EDINET API v2", "status": "connected", "notes": "EDINET index/cache/parser implemented; BIAP_EDINET_API_KEY is required for official FSA evidence and daily sync."},
    "KR": {"market": "Korea Exchange / global market feed", "filings": "FSS OpenDART", "status": "connected", "notes": "OpenDART annual statement adapter implemented; BIAP_OPENDART_API_KEY is required for official evidence."},
    "HK": {"market": "HKEX / global market feed", "filings": "issuer-owned consolidated statements; HKEXnews planned", "status": "partial", "notes": "Official issuer-owned FY2025 consolidated statements are connected for Hong Kong Exchanges and Clearing Limited (0388/388) only. Other HK tickers remain blocked without verified official evidence; generic HKEXnews ingestion is not claimed."},
    "SG": {"market": "SGX / global market feed", "filings": "issuer-owned financial results; SGXNet planned", "status": "partial", "notes": "Official issuer-owned fundamentals are connected for Singapore Exchange Limited (S68) only. Other SG tickers remain blocked unless they have a verified source. SGXNet generic ingestion is not enabled."},
    "IN": {"market": "NSE/BSE / global market feed", "filings": "NSE/BSE corporate filings", "status": "market-ready"},
    "SA": {"market": "Saudi Exchange / global market feed", "filings": "Saudi Exchange disclosures", "status": "market-ready"},
    "AE": {"market": "ADX/DFM / global market feed", "filings": "ADX financial summary + ADX/DFM disclosures", "status": "partial", "notes": "ADX structured annual summary is connected for net profit, equity, EPS and P/B. It is deliberately not treated as complete filing evidence; revenue, assets/liabilities and cash flow remain required. DFM official fundamentals are still planned."},
    "TR": {"market": "Borsa Istanbul / global market feed", "filings": "KAP Public Disclosure Platform", "status": "connected", "notes": "Official KAP BIST directory and public financial-summary pages are connected without a private API; BIAP uses only the latest completed annual column and keeps KAP's delay/correction caveat in provenance."},
    "ZA": {"market": "JSE / global market feed", "filings": "JSE SENS + issuer reports", "status": "market-ready"},
    "BR": {"market": "B3 / global market feed", "filings": "CVM DFP annual + CVM ITR quarterly open data", "status": "connected", "notes": "Official CVM DFP annual data and ITR quarterly corroboration are connected without API keys and refreshed from regulator datasets."},
}


def requirements_payload() -> list[dict]:
    return [
        {"key": item.key, "group": item.group, "critical": item.critical, "description": item.description}
        for item in ANALYSIS_REQUIREMENTS
    ]
