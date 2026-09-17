from __future__ import annotations

import pytest

from global_markets.gleif import GLEIFResolver, LEIResolution, _legal_core
from global_markets.providers import GlobalProviderError


def _row(lei: str, name: str, country: str) -> LEIResolution:
    return LEIResolution(
        lei=lei,
        legal_name=name,
        entity_status="ACTIVE",
        registration_status="ISSUED",
        source_url=f"https://example.test/{lei}",
        legal_jurisdiction=country,
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
