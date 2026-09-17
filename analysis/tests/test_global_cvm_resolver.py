from __future__ import annotations

import pytest

from global_markets.cvm_resolver import CVMResolvedFundamentalsProvider
from global_markets.providers import GlobalProviderError
from global_markets.runtime import build_registry


def _row(cnpj: str, legal_name: str) -> dict:
    return {
        "cnpj": cnpj,
        "legalName": legal_name,
        "periodEnd": "2025-12-31",
        "scope": "consolidated",
        "metrics": {"revenue": 1.0},
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


def test_runtime_uses_resolved_official_brazil_provider(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    registry = build_registry()
    provider = registry.fundamentals("BR", "B3")
    assert "cvm-open-data-dfp-resolved" in provider.provider_id
