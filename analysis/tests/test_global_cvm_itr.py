from __future__ import annotations

import json

from global_markets.cvm import _normalize_name
from global_markets.cvm_itr import CVMITRCorroborator
from global_markets.models import GlobalCompany
from global_markets.source_cache import source_index_path


def test_cvm_itr_adds_official_quarterly_source_without_overwriting_annual(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    legal_name = "PETROLEO BRASILEIRO S.A. - PETROBRAS"
    record = {
        "cnpj": "33000167000101",
        "scope": "consolidated",
        "periodEnd": "2026-06-30",
        "legalName": legal_name,
        "normalizedName": _normalize_name(legal_name),
        "currency": "BRL",
        "metrics": {"revenue": 250_000_000.0, "net_income": 40_000_000.0},
    }
    path = source_index_path("cvm-itr")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "updatedAt": "2026-09-18T00:00:00+00:00",
        "companies": {record["normalizedName"]: [record]},
    }), encoding="utf-8")

    company = GlobalCompany(
        country="BR", exchange="B3", mic_code="BVMF", currency="BRL",
        ticker="PETR4", name="Petrobras - Petroleo Brasileiro S.A.",
        revenue=1_000_000_000.0, net_income=120_000_000.0,
        filing_period_end="2025-12-31", report_scope="consolidated",
    )
    enriched = CVMITRCorroborator().corroborate(company)
    assert enriched.revenue == 1_000_000_000.0
    assert enriched.net_income == 120_000_000.0
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.raw_provider_fields["cvm_itr_period_end"] == "2026-06-30"
    assert enriched.sources[-1].provider == "cvm-open-data-itr"
    assert enriched.sources[-1].source_type == "official_quarterly_regulatory_financial_statement"
