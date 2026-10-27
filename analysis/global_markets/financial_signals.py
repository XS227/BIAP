"""Financial-sector evidence signals (ROE, ROA, equity/assets, P/B vs sector).

Banks, insurers and other financial issuers are not judged by operating-company
margins or leverage. These signals are computed only from officially reported
values already on the normalized company, only for issuers whose financial
classification is authoritative, and every figure carries its inputs so it can
be traced back to the filing. Nothing is estimated, averaged or defaulted: a
missing or non-positive input withholds the ratio and says why.

The signals add at most ONE evidence unit to the fundamental agent (see
``core_agents.fundamental_agent``); thresholds for acceptance are untouched.
"""
from __future__ import annotations

from typing import Optional

from .evidence_contract import STATUS_OFFICIAL_CURRENT, official_fundamental_sources, official_fundamental_status
from .models import GlobalCompany, taxonomy_financial_institution

# Classification sources that are an issuer-specific official/regulatory
# taxonomy, not a vendor label or crowd-sourced industry guess.
AUTHORITATIVE_SECTOR_SOURCES = frozenset({
    "sec-sic",
    "euronext-icb",
    "bme-sector-subsector",
    "deutsche-boerse-listed-companies",
})
_FINANCIAL_SECTOR_TOKENS = ("financial", "bank", "insurance")

# Ratios outside these bounds are almost always unit/scope errors, not facts.
_MAX_ABS_ROE = 1.0
_MAX_ABS_ROA = 0.25

MIN_PEER_PB_COUNT = 3


def classification_basis(company: GlobalCompany) -> Optional[str]:
    """Why this issuer is a financial institution, or None if it is not proven."""
    if taxonomy_financial_institution(company):
        return "filing_taxonomy:bank_net_interest_and_other_banking_income"
    source = str((company.raw_provider_fields or {}).get("sector_source") or "").strip().lower()
    text = " ".join(filter(None, (company.sector, company.industry))).lower()
    if source in AUTHORITATIVE_SECTOR_SOURCES and any(token in text for token in _FINANCIAL_SECTOR_TOKENS):
        return f"sector_reference:{source}"
    return None


def is_correctly_classified_financial(company: GlobalCompany) -> bool:
    return classification_basis(company) is not None


def _positive(value: Optional[float]) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def financial_metrics(company: GlobalCompany, *, now=None) -> Optional[dict]:
    """Traceable financial-sector ratios, or None when the issuer is not eligible.

    Eligible = authoritative financial classification AND an official, current
    fundamentals source. All ratios use the same filing period's year-end
    balances (not averages); the label says so.
    """
    basis = classification_basis(company)
    if basis is None:
        return None
    status, detail = official_fundamental_status(company, now=now)
    if not official_fundamental_sources(company) or status != STATUS_OFFICIAL_CURRENT:
        return {
            "applicable": False,
            "classificationBasis": basis,
            "reason": "no current official fundamentals; financial ratios not computed",
            "officialStatus": status,
            "metrics": {},
            "withheld": {},
        }
    best = max(official_fundamental_sources(company), key=lambda s: (str(s.period_end or ""), float(s.quality or 0.0)))
    inputs = {
        "netIncome": company.net_income,
        "totalEquity": company.total_equity,
        "totalAssets": company.total_assets,
    }
    metrics: dict = {}
    withheld: dict = {}

    def _put(name: str, value: Optional[float], formula: str, bound: Optional[float] = None) -> None:
        if value is None:
            return
        if bound is not None and abs(value) > bound:
            withheld[name] = f"implausible value {value:.4g} (> {bound:g}); not used, source values retained"
            return
        metrics[name] = {"value": round(value, 6), "formula": formula,
                         "basis": "period-end balance, not average"}

    if company.net_income is None:
        withheld["roe"] = withheld["roa"] = "net income not reported/extracted"
    if not _positive(company.total_equity):
        withheld["roe"] = withheld["equityToAssets"] = "total equity missing or not positive"
    if not _positive(company.total_assets):
        withheld["roa"] = withheld["equityToAssets"] = "total assets missing or not positive"

    if company.net_income is not None and _positive(company.total_equity):
        _put("roe", company.net_income / company.total_equity, "net_income / total_equity", _MAX_ABS_ROE)
    if company.net_income is not None and _positive(company.total_assets):
        _put("roa", company.net_income / company.total_assets, "net_income / total_assets", _MAX_ABS_ROA)
    if _positive(company.total_equity) and _positive(company.total_assets):
        if company.total_equity <= company.total_assets:
            _put("equityToAssets", company.total_equity / company.total_assets, "total_equity / total_assets")
        else:
            withheld["equityToAssets"] = "total equity exceeds total assets; scope mismatch, not used"

    benchmark = (company.raw_provider_fields or {}).get("peer_pb_benchmark")
    pb_block: Optional[dict] = None
    if _positive(company.pb) and isinstance(benchmark, dict):
        valid = (
            benchmark.get("scope") == "same_sector_scan_median"
            and _positive(benchmark.get("value"))
            and int(benchmark.get("count") or 0) >= MIN_PEER_PB_COUNT
        )
        if valid:
            relative = (company.pb / float(benchmark["value"]) - 1.0) * 100.0
            pb_block = {
                "pb": round(float(company.pb), 4),
                "sectorMedianPb": round(float(benchmark["value"]), 4),
                "peerCount": int(benchmark["count"]),
                "relativePct": round(relative, 2),
                "scope": benchmark["scope"],
                "cohort": benchmark.get("cohort"),
                "label": "derived comparison vs same-sector deep-analyzed scan median; not official filing evidence",
            }
        else:
            withheld["pbRelative"] = "no verified same-sector P/B benchmark (needs >=3 same-sector peers)"
    elif _positive(company.pb):
        withheld["pbRelative"] = "no verified same-sector P/B benchmark available"

    return {
        "applicable": True,
        "classificationBasis": basis,
        "metrics": metrics,
        "pbRelative": pb_block,
        "withheld": withheld,
        "inputs": inputs,
        "provenance": {
            "provider": best.provider,
            "sourceId": best.source_id,
            "sourceUrl": best.source_url,
            "periodEnd": company.filing_period_end,
            "isOfficial": True,
        },
        "reportingCurrency": company.reporting_currency,
        "officialStatus": status,
    }


def financial_fundamental_vote(company: GlobalCompany) -> tuple[float, list[str], int]:
    """(vote delta, reasons, evidence units) for the fundamental agent.

    Returns at most one evidence unit so this cannot inflate agent confidence
    beyond what a single additional verified source of information deserves.
    """
    data = financial_metrics(company)
    if not data or not data.get("applicable") or not data.get("metrics"):
        return 0.0, [], 0
    m = data["metrics"]
    vote = 0.0
    reasons: list[str] = []
    if "roe" in m:
        roe = m["roe"]["value"]
        reasons.append(f"ROE {roe * 100:.1f}% (reported net income / period-end equity)")
        if roe < 0:
            vote -= 0.3
        elif roe < 0.05:
            vote -= 0.1
        elif roe >= 0.10:
            vote += 0.15
    if "roa" in m:
        roa = m["roa"]["value"]
        reasons.append(f"ROA {roa * 100:.2f}%")
        if roa < 0:
            vote -= 0.1
        elif roa >= 0.008:
            vote += 0.05
    if "equityToAssets" in m:
        ratio = m["equityToAssets"]["value"]
        reasons.append(f"equity/assets {ratio * 100:.1f}%")
        if ratio < 0.04:
            vote -= 0.15
        elif ratio >= 0.08:
            vote += 0.05
    return vote, reasons, 1
