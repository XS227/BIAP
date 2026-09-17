from __future__ import annotations

import json

import pytest

from global_markets.cvm_resolver import CVMResolvedFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.runtime import build_registry
from global_markets.source_cache import source_index_path


def _row(cnpj: str, legal_name: str) -> dict:
    return {
        "cnpj": cnpj,
        "legalName": legal_name,
        "periodEnd": "2025-12-31",
        "scope": "consolidated",
        "metrics": {
            "revenue": 1_000_000.0,
            "net_income": 150_000.0,
            "total_assets": 4_000_000.0,
            "total_equity": 2_000_000.0,
            "operating_cash_flow": 250_000.0,
        },
    }


def test_resolver_accepts_unique_brand_plus_b3_share_class():
    companies = {
        "petroleo brasileiro s a petrobras": [
            _row("33000167000101", "PETROLEO BRASILEIRO S.A. - PETROBRAS")
        ],
        "vale s a": [_row("33592510000154", "VALE S.A.")],
    }
    rows, mode = CVMResolvedFundamentalsProvider._resolve_rows(companies, "PETROBRAS PN N2")
    assert {row["cnpj"] for row in rows} == {"33000167000101"}
    assert mode == "unique_business_token_containment"


def test_resolver_accepts_reordered_full_business_name_without_fuzzy_spelling():
    companies = {
        "petroleo brasileiro s a petrobras": [
            _row("33000167000101", "PETROLEO BRASILEIRO S.A. - PETROBRAS")
        ],
    }
    rows, mode = CVMResolvedFundamentalsProvider._resolve_rows(
        companies, "Petrobras - Petroleo Brasileiro S.A."
    )
    assert {row["cnpj"] for row in rows} == {"33000167000101"}
    assert mode in {"exact_business_token_signature", "unique_business_token_containment"}


def test_resolver_rejects_brand_token_when_multiple_cnpjs_share_it():
    companies = {
        "alpha energia s a": [_row("11111111000111", "ALPHA ENERGIA S.A.")],
        "alpha participacoes s a": [_row("22222222000122", "ALPHA PARTICIPACOES S.A.")],
    }
    with pytest.raises(GlobalProviderError):
        CVMResolvedFundamentalsProvider._resolve_rows(companies, "ALPHA PN")


def test_resolved_provider_enriches_abbreviated_b3_name_with_official_cvm(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    legal_name = "PETROLEO BRASILEIRO S.A. - PETROBRAS"
    row = _row("33000167000101", legal_name)
    index = {
        "updatedAt": "2026-09-18T00:00:00+00:00",
        "companies": {"petroleo brasileiro s a petrobras": [row]},
    }
    path = source_index_path("cvm-dfp")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")

    seed = GlobalCompany(
        country="BR",
        exchange="B3",
        mic_code="BVMF",
        currency="BRL",
        ticker="PETR4",
        name="PETROBRAS PN N2",
    )
    enriched = CVMResolvedFundamentalsProvider().enrich_fundamentals(seed)

    assert enriched.revenue == 1_000_000.0
    assert enriched.net_income == 150_000.0
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.raw_provider_fields["cvm_cnpj"] == "33000167000101"
    assert enriched.raw_provider_fields["cvm_match_mode"] == "unique_business_token_containment"
    source = enriched.sources[-1]
    assert source.provider == "cvm-open-data-dfp-resolved"
    assert source.source_type == "official_regulatory_financial_statement"


def test_runtime_uses_resolved_official_brazil_provider(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    registry = build_registry()
    provider = registry.fundamentals("BR", "B3")
    assert "cvm-open-data-dfp-resolved" in provider.provider_id
