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


def _company(country: str, name: str, ticker: str = "TEST") -> GlobalCompany:
    return GlobalCompany(
        country=country,
        exchange="TEST_EXCHANGE",
        mic_code="TEST",
        currency="EUR",
        ticker=ticker,
        name=name,
    )


def test_legal_core_handles_diacritics_and_punctuated_legal_forms():
    assert _legal_core("L'Oréal S.A.") == "LOREAL"
    assert _legal_core("LVMH Moët Hennessy Louis Vuitton SE") == "LVMHMOETHENNESSYLOUISVUITTON"
    assert _legal_core("Enel S.p.A.") == "ENEL"


def test_legal_core_handles_swedish_prefix_form():
    assert _legal_core("Volvo AB") == "VOLVO"
    assert _legal_core("Aktiebolaget Volvo") == "VOLVO"


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
