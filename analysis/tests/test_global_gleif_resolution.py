from __future__ import annotations

import pytest

from global_markets.esef_country import CountryAwareESEFFundamentalsProvider
from global_markets.gleif import GLEIFResolver, LEIResolution, _legal_core
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError


def _row(lei: str, name: str, country: str | None) -> LEIResolution:
    return LEIResolution(
        lei=lei,
        legal_name=name,
        entity_status="ACTIVE",
        registration_status="ISSUED",
        source_url=f"https://example.test/{lei}",
        legal_jurisdiction=country,
    )


def _company(country: str, name: str, ticker: str = "TEST", isin: str | None = None) -> GlobalCompany:
    return GlobalCompany(
        country=country,
        exchange="TEST_EXCHANGE",
        mic_code="TEST",
        currency="EUR",
        ticker=ticker,
        name=name,
        isin=isin,
    )


def test_gleif_resolves_unique_active_issuer_by_isin(monkeypatch):
    resolver = GLEIFResolver()

    def fake_get(path, params=None):
        assert path == "lei-records"
        assert params["filter[isin]"] == "SE0000106270"
        return {
            "data": [{
                "id": "529900O5RR7R39FRDM42",
                "attributes": {
                    "entity": {
                        "legalName": {"name": "H & M Hennes & Mauritz AB"},
                        "status": "ACTIVE",
                        "legalJurisdiction": "SE",
                    },
                    "registration": {"status": "ISSUED"},
                },
            }]
        }

    monkeypatch.setattr(resolver, "_get", fake_get)
    match = resolver.resolve_isin("SE0000106270", country="SE")
    assert match.lei == "529900O5RR7R39FRDM42"
    assert match.legal_name == "H & M Hennes & Mauritz AB"


def test_esef_prefers_isin_to_lei_before_display_name(monkeypatch):
    provider = CountryAwareESEFFundamentalsProvider()
    seen = []

    def fake_isin(isin, country=None):
        seen.append((isin, country))
        return _row("635400BR2ROC1FVEBQ56", "Ryanair Holdings Public Limited Company", "IE")

    monkeypatch.setattr(provider.gleif, "resolve_isin", fake_isin)
    monkeypatch.setattr(
        provider.gleif,
        "resolve_exact_legal_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("name fallback should not run")),
    )
    lei, legal_name = provider._resolve_lei(
        _company("IE", "RYANAIR HOLD. PLC", "RYA", isin="IE00BYTBXV33")
    )
    assert lei == "635400BR2ROC1FVEBQ56"
    assert legal_name == "Ryanair Holdings Public Limited Company"
    assert seen == [("IE00BYTBXV33", "IE")]


def test_legal_core_handles_diacritics_and_punctuated_legal_forms():
    assert _legal_core("L'Oréal S.A.") == "LOREAL"
    assert _legal_core("LVMH Moët Hennessy Louis Vuitton SE") == "LVMHMOETHENNESSYLOUISVUITTON"
    assert _legal_core("Enel S.p.A.") == "ENEL"


def test_legal_core_handles_german_spelled_out_legal_form():
    assert _legal_core("Siemens AG") == "SIEMENS"
    assert _legal_core("Siemens Aktiengesellschaft") == "SIEMENS"


def test_german_ag_abbreviation_resolves_to_spelled_out_legal_name(monkeypatch):
    resolver = GLEIFResolver()
    rows = [_row("W38RGI023J3WT1HWRP32", "Siemens Aktiengesellschaft", "DE")]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    match = resolver.resolve_exact_legal_name("Siemens AG", country="DE")
    assert match.lei == "W38RGI023J3WT1HWRP32"
    assert match.legal_name == "Siemens Aktiengesellschaft"


def test_legal_core_handles_swedish_prefix_form():
    assert _legal_core("Volvo AB") == "VOLVO"
    assert _legal_core("Aktiebolaget Volvo") == "VOLVO"
    assert _legal_core("Atlas Copco Aktiebolag") == "ATLASCOPCO"
    assert _legal_core("Investor AB (publ)") == "INVESTOR"
    assert _legal_core("Atlas Copco AB ser. B") == "ATLASCOPCO"


def test_swedish_abbreviation_resolves_to_aktiebolag_legal_name(monkeypatch):
    resolver = GLEIFResolver()
    rows = [
        _row("213800T8PC8Q4FYJZR07", "ATLAS COPCO AKTIEBOLAG", "SE"),
        _row("54930088FQENVUEVRG70", "ATLAS COPCO LIMITED", "GB"),
    ]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    match = resolver.resolve_exact_legal_name("Atlas Copco AB", country="SE")
    assert match.lei == "213800T8PC8Q4FYJZR07"


def test_exact_duplicate_is_safely_narrowed_by_legal_jurisdiction(monkeypatch):
    resolver = GLEIFResolver()
    rows = [
        _row("11111111111111111111", "Banco Santander, S.A.", "ES"),
        _row("22222222222222222222", "Banco Santander, S.A.", "MX"),
        _row("33333333333333333333", "Banco Santander, S.A.", "AR"),
    ]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    match = resolver.resolve_exact_legal_name("Banco Santander, S.A.", country="ES")
    assert match.lei == "11111111111111111111"


def test_exact_duplicate_stays_blocked_without_country(monkeypatch):
    resolver = GLEIFResolver()
    rows = [
        _row("11111111111111111111", "Banco Santander, S.A.", "ES"),
        _row("22222222222222222222", "Banco Santander, S.A.", "MX"),
    ]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    with pytest.raises(GlobalProviderError, match="ambiguous"):
        resolver.resolve_exact_legal_name("Banco Santander, S.A.")


def test_legal_form_normalization_can_match_spelled_out_swedish_form(monkeypatch):
    resolver = GLEIFResolver()
    rows = [_row("44444444444444444444", "Aktiebolaget Volvo", "SE")]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    match = resolver.resolve_exact_legal_name("Volvo AB", country="SE")
    assert match.lei == "44444444444444444444"


def test_esef_country_filing_can_disambiguate_same_legal_core(monkeypatch):
    provider = CountryAwareESEFFundamentalsProvider()
    rows = [
        _row("11111111111111111111", "LVMH MOET HENNESSY LOUIS VUITTON", None),
        _row("22222222222222222222", "LVMH MOET HENNESSY LOUIS VUITTON INC.", None),
    ]
    monkeypatch.setattr(
        provider.gleif,
        "resolve_exact_legal_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(GlobalProviderError("ambiguous")),
    )
    monkeypatch.setattr(provider.gleif, "_search", lambda *args, **kwargs: rows)
    monkeypatch.setattr(provider, "_country_filing_exists", lambda lei, country: lei == "11111111111111111111")

    lei, legal_name = provider._resolve_lei(_company("FR", "LVMH Moët Hennessy Louis Vuitton SE", "MC"))
    assert lei == "11111111111111111111"
    assert legal_name == "LVMH MOET HENNESSY LOUIS VUITTON"


def test_esef_country_filing_never_guesses_when_two_candidates_match(monkeypatch):
    provider = CountryAwareESEFFundamentalsProvider()
    rows = [
        _row("11111111111111111111", "Banco Santander, S.A.", None),
        _row("22222222222222222222", "Banco Santander S.A.", None),
    ]
    monkeypatch.setattr(
        provider.gleif,
        "resolve_exact_legal_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(GlobalProviderError("ambiguous")),
    )
    monkeypatch.setattr(provider.gleif, "_search", lambda *args, **kwargs: rows)
    monkeypatch.setattr(provider, "_country_filing_exists", lambda lei, country: True)

    with pytest.raises(GlobalProviderError, match="ambiguous"):
        provider._resolve_lei(_company("ES", "Banco Santander, S.A.", "SAN"))


def test_legal_core_strips_market_share_class_descriptor():
    assert _legal_core("Aker ASA Series A Shares") == "AKER"
    assert _legal_core("Example AB Class B Shares") == "EXAMPLE"


def test_share_class_display_name_resolves_to_issuer_legal_name(monkeypatch):
    resolver = GLEIFResolver()
    rows = [_row("549300EXAMPLE00000001", "Aker ASA", "NO")]
    monkeypatch.setattr(resolver, "_search", lambda *args, **kwargs: rows)

    match = resolver.resolve_exact_legal_name("Aker ASA Series A Shares", country="NO")
    assert match.legal_name == "Aker ASA"


def test_apostrophe_query_variant_can_resolve_loreal(monkeypatch):
    resolver = GLEIFResolver()
    queries = []

    def fake_search(text, page_size=100):
        queries.append(text)
        if text == "L'OREAL":
            return [_row("529900JI1GG6F7RKVI53", "L'OREAL", "FR")]
        return []

    monkeypatch.setattr(resolver, "_search", fake_search)
    match = resolver.resolve_exact_legal_name("L'Oréal S.A.", country="FR")
    assert match.lei == "529900JI1GG6F7RKVI53"
    assert "L'OREAL" in queries


def test_esef_uses_verified_hm_catalog_alias(monkeypatch):
    provider = CountryAwareESEFFundamentalsProvider()
    seen = []

    def fake_resolve(name, country=None):
        seen.append((name, country))
        assert name == "H & M Hennes & Mauritz AB"
        return _row("529900O5RR7R39FRDM42", "H & M Hennes & Mauritz AB", "SE")

    monkeypatch.setattr(provider.gleif, "resolve_exact_legal_name", fake_resolve)
    lei, legal_name = provider._resolve_lei(_company("SE", "Hennes & Mauritz AB", "HM.B"))
    assert lei == "529900O5RR7R39FRDM42"
    assert legal_name == "H & M Hennes & Mauritz AB"
    assert seen == [("H & M Hennes & Mauritz AB", "SE")]
