from pathlib import Path

def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path)
    text=p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old,new,1),encoding="utf-8")

replace_once(
    "analysis/global_markets/jpx_official.py",
    '''                raw_provider_fields={
                    "official_universe": True,
''',
    '''                raw_provider_fields={
                    "official_universe": True,
                    "trusted_official_equity": True,
''',
)

replace_once(
    "analysis/global_markets/cached_universe.py",
    '''            normalized_row = {
                "name": str(row.get("name") or ticker),
                "type": str(row.get("instrument_type") or "Common Stock"),
                "cfi_code": cached_raw.get("cfi"),
            }
''',
    '''            normalized_row = {
                "name": str(row.get("name") or ticker),
                "type": str(row.get("instrument_type") or "Common Stock"),
                "cfi_code": cached_raw.get("cfi"),
                "trusted_official_equity": cached_raw.get("trusted_official_equity") is True,
            }
''',
)

replace_once(
    "analysis/global_markets/universe.py",
    '''    if ".PR." in ticker or ticker.endswith(".PR") or ".RT." in ticker or ticker.endswith(".RT"):
        return False

    if country.upper() in {"FR", "IT", "NL", "BE", "IE", "PT", "ES"} and re.fullmatch(r"[0-9]{4,}[A-Z]?", ticker):
''',
    '''    if ".PR." in ticker or ticker.endswith(".PR") or ".RT." in ticker or ticker.endswith(".RT"):
        return False

    # A narrowly-scoped official adapter may certify an instrument after applying
    # the exchange's own product/segment rules. Preserve the universal structural
    # checks above, then bypass vendor-name heuristics only for that explicit
    # certification. JPX uses this for domestic Prime/Standard/Growth four-code
    # ordinary shares; e.g. "note inc." is a company, not a debt Note.
    if row.get("trusted_official_equity") is True:
        return True

    if country.upper() in {"FR", "IT", "NL", "BE", "IE", "PT", "ES"} and re.fullmatch(r"[0-9]{4,}[A-Z]?", ticker):
''',
)

p=Path("analysis/tests/test_global_universe_cache_v8.py")
text=p.read_text(encoding="utf-8")
addition=r'''

def test_trusted_official_jpx_equity_is_not_rejected_for_company_name_note(tmp_path: Path):
    class TrustedJPXSource(InstrumentUniverseProvider):
        provider_id = "official-jpx-test"
        def list_instruments(self, *, country=None, exchange=None):
            return [GlobalCompany(
                country="JP", exchange="TSE_JP", currency="JPY",
                ticker="5243", name="note inc.", mic_code="XJPX",
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "trusted_official_equity": True,
                },
            )]

    provider = PersistentUniverseProvider(
        TrustedJPXSource(), data_dir=str(tmp_path), fresh_hours=12
    )
    rows = list(provider.refresh(country="JP", exchange="TSE_JP"))
    assert len(rows) == 1
    assert rows[0].ticker == "5243"
    assert rows[0].name == "note inc."


def test_untrusted_note_name_remains_rejected(tmp_path: Path):
    class UntrustedSource(InstrumentUniverseProvider):
        provider_id = "reference-test"
        def list_instruments(self, *, country=None, exchange=None):
            return [GlobalCompany(
                country="JP", exchange="TSE_JP", currency="JPY",
                ticker="5243", name="note inc.", mic_code="XJPX",
                instrument_type="Common Stock",
            )]

    provider = PersistentUniverseProvider(
        UntrustedSource(), data_dir=str(tmp_path), fresh_hours=12
    )
    rows = list(provider.refresh(country="JP", exchange="TSE_JP"))
    assert rows == []
'''
if "test_trusted_official_jpx_equity_is_not_rejected_for_company_name_note" not in text:
    p.write_text(text+addition,encoding="utf-8")
