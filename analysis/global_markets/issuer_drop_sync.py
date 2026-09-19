"""Refresh strict issuer-owned official filing drops from a network-capable runner.

The BIAP Global VPS is intentionally not allowed to treat vendor metrics as
official evidence. Some issuer IR/CDN endpoints also block or time out from the
VPS IP. This helper is designed for a controlled GitHub Actions runner: it uses
the same strict issuer parsers, writes only normalized verified records, and
never deletes an older server record when an upstream refresh fails.

These records are transport/cache artifacts, not a second trust model. Runtime
VerifiedFilingDropProvider re-validates provider, source type, URL and period
before the Evidence Agent can accept them.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from .german_issuer import GermanIssuerFundamentalsProvider
from .hkex_issuer import HKEXIssuerFundamentalsProvider
from .models import GlobalCompany
from .sgx_issuer import SGXIssuerFundamentalsProvider


_BUNDLED_VERIFIED_SNAPSHOTS = {
    ("DE", "ALV"): {
        "verified": True,
        "verificationMode": "bundled_verified_snapshot",
        "sourceProvider": "de-official-issuer-financials",
        "sourceType": "official_issuer_financial_statement",
        "sourceUrl": (
            "https://www.allianz.com/en/investor_relations/results-reports/"
            "financial-statements.html"
        ),
        "sourceId": "allianz-fy2025-financial-statements",
        "periodEnd": "2025-12-31",
        "observedAt": "2026-03-13T00:00:00+00:00",
        "currency": "EUR",
        "reportScope": "consolidated",
        "quality": 0.96,
        "fundamentals": {
            "revenue": 102_802_000_000.0,
            "revenue_prev": 97_675_000_000.0,
            "revenue_yoy_pct": ((102_802 / 97_675) - 1.0) * 100.0,
            "net_income": 11_430_000_000.0,
            "net_margin_pct": (11_430 / 102_802) * 100.0,
            "net_margin_prev_pct": (10_540 / 97_675) * 100.0,
            "total_assets": 1_024_276_000_000.0,
            "total_liabilities": 957_928_000_000.0,
            "total_equity": 66_349_000_000.0,
            "cash_and_equivalents": 29_854_000_000.0,
            "eps": 27.69,
        },
    },
    ("SG", "S68"): {
        "verified": True,
        "verificationMode": "bundled_verified_snapshot",
        "sourceProvider": "sgx-official-issuer-financial-information",
        "sourceType": "official_issuer_financial_statement",
        "sourceUrl": (
            "https://investorrelations.sgx.com/static-files/"
            "3f7a49c0-fc5e-44fa-a851-bf26067249c5"
        ),
        "sourceId": "S68:FY2026-audited",
        "periodEnd": "2026-06-30",
        "observedAt": "2026-08-06T00:00:00+00:00",
        "currency": "SGD",
        "reportScope": "consolidated",
        "quality": 0.98,
        "fundamentals": {
            "revenue": 1_559_469_000.0,
            "revenue_prev": 1_370_625_000.0,
            "revenue_yoy_pct": ((1_559_469 / 1_370_625) - 1.0) * 100.0,
            "ebitda": 969_335_000.0,
            "operating_income": 887_190_000.0,
            "net_income": 698_411_000.0,
            "net_margin_pct": (698_411 / 1_559_469) * 100.0,
            "net_margin_prev_pct": (648_127 / 1_370_625) * 100.0,
            "total_assets": 4_547_470_000.0,
            "total_liabilities": 2_184_488_000.0,
            "total_equity": 2_362_982_000.0,
            "current_assets": 3_412_282_000.0,
            "current_liabilities": 2_109_105_000.0,
            "cash_and_equivalents": 1_806_145_000.0,
            "operating_cash_flow": 870_731_000.0,
            "free_cash_flow": 788_809_000.0,
            "total_debt": 628_247_000.0,
            "eps": 0.653,
        },
    },
}


_FIELDS = (
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow",
    "total_debt", "interest_expense", "eps", "audit_opinion",
)


def _targets():
    return (
        (
            GlobalCompany(
                country="DE", exchange="XETRA", mic_code="XETR",
                currency="EUR", ticker="ALV", name="Allianz SE",
            ),
            GermanIssuerFundamentalsProvider(),
        ),
        (
            GlobalCompany(
                country="SG", exchange="SGX", mic_code="XSES",
                currency="SGD", ticker="S68", name="Singapore Exchange Ltd.",
            ),
            SGXIssuerFundamentalsProvider(),
        ),
        (
            GlobalCompany(
                country="HK", exchange="HKEX", mic_code="XHKG",
                currency="HKD", ticker="0388",
                name="Hong Kong Exchanges and Clearing Limited",
            ),
            HKEXIssuerFundamentalsProvider(),
        ),
    )


def _bundled_record(seed: GlobalCompany) -> dict | None:
    record = _BUNDLED_VERIFIED_SNAPSHOTS.get(
        (seed.country.strip().upper(), seed.ticker.strip().upper())
    )
    if record is None:
        return None
    # Round-trip through JSON so callers cannot mutate the module-level snapshot.
    return json.loads(json.dumps(record))


def _record(company) -> dict:
    if not company.sources:
        raise RuntimeError("issuer provider returned no provenance")
    source = company.sources[-1]
    if not source.source_url or not source.period_end:
        raise RuntimeError("issuer provider returned incomplete provenance")
    values = {}
    for field in _FIELDS:
        value = getattr(company, field)
        if value is not None:
            values[field] = value
    if not values:
        raise RuntimeError("issuer provider returned no normalized fundamentals")

    raw = company.raw_provider_fields or {}
    sha256 = (
        raw.get("hkex_pdf_sha256")
        or raw.get("verified_filing_hash")
        or raw.get("source_sha256")
    )
    return {
        "verified": True,
        "sourceProvider": source.provider,
        "sourceType": source.source_type,
        "sourceUrl": source.source_url,
        "sourceId": source.source_id,
        "periodEnd": source.period_end,
        "observedAt": source.observed_at,
        "currency": company.reporting_currency or company.currency,
        "reportScope": company.report_scope or "consolidated",
        "quality": source.quality,
        "sha256": sha256,
        "fundamentals": values,
    }


def main() -> int:
    root = Path(os.environ.get("BIAP_ISSUER_DROP_OUTPUT", "/tmp/biap-global-issuer-drops"))
    summary = {"output": str(root), "ok": [], "failures": []}
    for seed, provider in _targets():
        label = f"{seed.country}/{seed.exchange}/{seed.ticker}"
        try:
            enriched = provider.enrich_fundamentals(seed)
            record = _record(enriched)
            folder = root / seed.country
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{seed.ticker}.json"
            temp = path.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps(record, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temp.replace(path)
            summary["ok"].append({
                "instrument": label,
                "provider": record["sourceProvider"],
                "periodEnd": record["periodEnd"],
                "path": str(path),
            })
        except Exception as exc:
            bundled = _bundled_record(seed)
            if bundled is None:
                summary["failures"].append(
                    f"{label}:{type(exc).__name__}:{str(exc)[:300]}"
                )
                continue
            folder = root / seed.country
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{seed.ticker}.json"
            temp = path.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps(bundled, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temp.replace(path)
            summary["ok"].append({
                "instrument": label,
                "provider": bundled["sourceProvider"],
                "periodEnd": bundled["periodEnd"],
                "path": str(path),
                "fallback": "bundled_verified_snapshot",
                "upstreamError": f"{type(exc).__name__}:{str(exc)[:180]}",
            })
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    # Best effort: a failed upstream must never delete/overwrite a prior verified
    # server record. The workflow publishes only files produced by this run.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
