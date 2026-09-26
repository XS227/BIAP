"""Current audited JSE fundamentals from verified SEC XBRL filings."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
import xml.etree.ElementTree as ET

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_PROVIDER_ID = "official-jse-current-20f-v2"
_SSW_2025 = "https://www.sec.gov/Archives/edgar/data/1786909/000162828026026991/sbsw-20251231_htm.xml"
_USER_AGENT = (
    os.environ.get("BIAP_SEC_USER_AGENT")
    or "BIAP Global research application (+https://setai.no)"
).strip()
_PERIOD = "2025-12-31"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sibanye_2025_xbrl(xml_bytes: bytes) -> dict[str, float]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise GlobalProviderError("Sibanye FY2025 extracted XBRL is invalid") from exc

    valid_contexts: set[str] = set()
    for node in root.iter():
        if _local(node.tag) != "context":
            continue
        context_id = str(node.attrib.get("id") or "")
        ends = [str(x.text or "").strip() for x in node.iter() if _local(x.tag) in {"endDate", "instant"}]
        if _PERIOD in ends:
            valid_contexts.add(context_id)
    if not valid_contexts:
        raise GlobalProviderError("Sibanye FY2025 XBRL has no verified reporting-period context")

    facts: dict[str, list[float]] = {}
    for node in root.iter():
        context = str(node.attrib.get("contextRef") or "")
        if context not in valid_contexts:
            continue
        name = _local(node.tag)
        raw = str(node.text or "").strip().replace(",", "")
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        facts.setdefault(name, []).append(value)

    def pick(*concepts: str) -> float:
        for concept in concepts:
            values = facts.get(concept) or []
            if values:
                # Consolidated primary-statement fact is normally repeated in
                # several presentation contexts with the same value. Prefer the
                # largest absolute magnitude to avoid per-share/segment facts.
                return max(values, key=abs)
        raise GlobalProviderError(f"Sibanye FY2025 XBRL concept missing: {concepts[0]}")

    revenue = pick("Revenue", "RevenueFromContractsWithCustomers")
    net_income = pick("ProfitLossAttributableToOwnersOfParent", "ProfitLoss")
    assets = pick("Assets")
    liabilities = pick("Liabilities")
    equity = pick("Equity")
    cash = pick("CashAndCashEquivalents")

    # Independent audited values visible in the filed 20-F provide a narrow
    # sanity envelope against selecting an unintended dimensional context.
    expected = {
        "revenue": 129_677_000_000.0,
        "net_income": -5_171_000_000.0,
        "total_assets": 149_737_000_000.0,
        "total_liabilities": 105_570_000_000.0,
        "total_equity": 44_167_000_000.0,
        "cash_and_equivalents": 17_178_000_000.0,
    }
    actual = {
        "revenue": revenue,
        "net_income": net_income,
        "total_assets": assets,
        "total_liabilities": liabilities,
        "total_equity": equity,
        "cash_and_equivalents": cash,
    }
    for key, target in expected.items():
        if abs(actual[key] - target) > max(1.0, abs(target) * 0.000001):
            raise GlobalProviderError(f"Sibanye FY2025 XBRL sanity check failed: {key}")
    return actual


class JSEIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 90.0) -> None:
        self.timeout = max(10.0, float(timeout))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper(), company.ticker.upper()) != ("ZA", "JSE", "SSW"):
            raise GlobalProviderError(f"JSE current filing fundamentals are not verified for {company.ticker}")
        try:
            response = requests.get(
                _SSW_2025,
                headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Sibanye current XBRL request failed: {type(exc).__name__}") from exc

        metrics = parse_sibanye_2025_xbrl(response.content)
        observed = datetime.now(timezone.utc).isoformat()
        revenue = metrics["revenue"]
        net_income = metrics["net_income"]
        enriched = replace(
            company,
            reporting_currency="ZAR",
            revenue=revenue,
            net_income=net_income,
            net_margin_pct=net_income / revenue * 100.0,
            total_assets=metrics["total_assets"],
            total_liabilities=metrics["total_liabilities"],
            total_equity=metrics["total_equity"],
            cash_and_equivalents=metrics["cash_and_equivalents"],
            filing_period_end=_PERIOD,
            filing_observed_at="2026-04-24",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "jse_current_20f_xbrl_url": _SSW_2025,
                "jse_current_20f_xbrl_verified": True,
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id="SEC:SBSW:20-F:2025-12-31",
                source_url=_SSW_2025,
                observed_at=observed,
                period_end=_PERIOD,
                quality=1.0,
                notes="SEC extracted XBRL instance from audited Sibanye-Stillwater FY2025 Form 20-F.",
            ),
        )
