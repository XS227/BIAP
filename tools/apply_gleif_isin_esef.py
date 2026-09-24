from pathlib import Path

def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once(
    "analysis/global_markets/gleif.py",
    '''    def _search(self, text: str, *, page_size: int = 100) -> list[LEIResolution]:
''',
    '''    def resolve_isin(self, isin: str, *, country: Optional[str] = None) -> LEIResolution:
        """Resolve an issuer LEI from GLEIF's certified ISIN mapping.

        ISIN is a stronger issuer-identity key than a market display name. We
        still require one unique active/usable LEI (optionally narrowed by legal
        jurisdiction); ambiguous mappings remain blocked.
        """
        wanted = str(isin or "").strip().upper()
        if len(wanted) != 12 or not wanted.isalnum():
            raise GlobalProviderError("invalid ISIN format")
        payload = self._get(
            "lei-records",
            {
                "filter[isin]": wanted,
                "page[size]": 100,
                "page[number]": 1,
            },
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise GlobalProviderError("GLEIF ISIN search returned no data list")
        matches: list[LEIResolution] = []
        for row in rows:
            resolution = self._resolution(row)
            if resolution is not None and self._usable(resolution):
                matches.append(resolution)
        resolved, count = self._unique_or_country(matches, country=country)
        if resolved is None:
            raise GlobalProviderError(
                f"GLEIF ISIN resolution for {wanted!r} is ambiguous/unavailable ({count} active matches)"
            )
        return resolved

    def _search(self, text: str, *, page_size: int = 100) -> list[LEIResolution]:
''',
)

replace_once(
    "analysis/global_markets/esef_country.py",
    '''        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name
        if not company.name or company.name == company.ticker:
''',
    '''        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name

        # Prefer the regulator/numbering-agency identity chain over display-name
        # matching. GLEIF exposes certified ISIN->LEI mappings; when present and
        # unique this avoids brittle issuer-name aliases (share classes,
        # abbreviations, punctuation and local legal forms).
        if company.isin:
            try:
                resolution = self.gleif.resolve_isin(company.isin, country=company.country)
                return resolution.lei, resolution.legal_name
            except GlobalProviderError:
                # Not every legacy ISIN is mapped by participating NNAs yet.
                # Fall back conservatively to the existing exact-name resolver.
                pass

        if not company.name or company.name == company.ticker:
''',
)

replace_once(
    "analysis/tests/test_global_gleif_resolution.py",
    '''def _company(country: str, name: str, ticker: str = "TEST") -> GlobalCompany:
    return GlobalCompany(
        country=country,
        exchange="TEST_EXCHANGE",
        mic_code="TEST",
        currency="EUR",
        ticker=ticker,
        name=name,
    )
''',
    '''def _company(country: str, name: str, ticker: str = "TEST", isin: str | None = None) -> GlobalCompany:
    return GlobalCompany(
        country=country,
        exchange="TEST_EXCHANGE",
        mic_code="TEST",
        currency="EUR",
        ticker=ticker,
        name=name,
        isin=isin,
    )
''',
)

p = Path("analysis/tests/test_global_gleif_resolution.py")
text = p.read_text(encoding="utf-8")
marker = '''def test_legal_core_handles_diacritics_and_punctuated_legal_forms():
'''
addition = '''def test_gleif_resolves_unique_active_issuer_by_isin(monkeypatch):
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


'''
if addition not in text:
    if marker not in text:
        raise SystemExit("test insertion marker missing")
    text = text.replace(marker, addition + marker, 1)
    p.write_text(text, encoding="utf-8")
