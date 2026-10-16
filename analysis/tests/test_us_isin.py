import pytest

from global_markets.us_isin import isin_from_cusip, issuer_tokens, match_13f_rows, resolve_us_isin

ROWS = [
    ("037833100", "APPLE INC", "COM"),
    ("037833900", "APPLE INC", "CALL"),
    ("02079K107", "ALPHABET INC", "CAP STK CL C"),
    ("02079K305", "ALPHABET INC", "CAP STK CL A"),
    ("478160104", "JOHNSON & JOHNSON", "COM"),
    ("46620W201", "JOHNSON CTLS INTL PLC", "SHS"),
    ("N07059210", "ASML HLDG NV", "N Y REGISTRY SHS"),
    ("291011104", "EMERSON ELEC CO", "COM"),
    ("343927307", "EMERSON ELEC CO", "COM"),
]


@pytest.mark.parametrize("cusip,isin", [
    ("037833100", "US0378331005"),
    ("594918104", "US5949181045"),
    ("02079K305", "US02079K3059"),
    ("N07059210", "USN070592100"),
])
def test_check_digit_matches_published_isins(cusip, isin):
    assert isin_from_cusip(cusip) == isin


def test_invalid_cusip_is_rejected():
    assert isin_from_cusip("123") is None
    assert isin_from_cusip("037833100", prefix="USA") is None


def test_unique_exact_match_resolves_and_ignores_options():
    assert resolve_us_isin("Apple Inc. - Common Stock", ROWS) == "US0378331005"


def test_share_class_disambiguates():
    assert resolve_us_isin("Alphabet Inc. - Class A Common Stock", ROWS, share_class="A") == "US02079K3059"
    assert resolve_us_isin("Alphabet Inc.", ROWS) is None  # two classes, no class given -> not guessed


def test_ampersand_name_is_exact_not_fuzzy():
    assert resolve_us_isin("Johnson & Johnson Common Stock", ROWS) == "US4781601046"


def test_abbreviated_issuer_resolves_but_ambiguity_stays_unresolved():
    assert resolve_us_isin("ASML Holding N.V. - New York Registry Shares", ROWS) == "USN070592100"
    assert resolve_us_isin("Emerson Electric Company", ROWS) is None
    assert len(match_13f_rows("Emerson Electric Company", ROWS)) == 2


def test_tokens_drop_legal_suffixes():
    assert issuer_tokens("Walt Disney Company (The) Common Stock") == ["WALT", "DISNEY"]
