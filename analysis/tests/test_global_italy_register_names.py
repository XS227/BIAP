"""Italian storage issuer-register matching from GLEIF legal names.

GLEIF keeps statutory clauses in the legal name that the 1INFO / eMarket
STORAGE registers omit. Variants are derived only from the GLEIF name, a
register id is accepted only when it is the single match across all variants,
and the downloaded report's embedded LEI remains the hard identity gate.
"""
import pytest

from global_markets.oam_esef import _it_name_variants, _it_unique_register_id
from global_markets.providers import GlobalProviderError

ONEINFO = [("79", "C.I.R."), ("110", "DANIELI & C."), ("22", "AUTOSTRADE MERIDIONALI"), ("9", "A2A"), ("33", "INTESA SANPAOLO")]
EMARKET = [("121", "C.I.R."), ("89", "CIR"), ("3327", "DANIELI & C."), ("306512", "ICOP"), ("142", "INTESA SANPAOLO")]


@pytest.mark.parametrize("legal_name, register, expected", [
    ("CIR S.P.A. - COMPAGNIE INDUSTRIALI RIUNITE", ONEINFO, "79"),
    ('DANIELI & C. OFFICINE MECCANICHE S.P.A. IN FORMA ABBREVIATA ANCHE "DANIELI & C. S.P.A."', ONEINFO, "110"),
    ('DANIELI & C. OFFICINE MECCANICHE S.P.A. IN FORMA ABBREVIATA ANCHE "DANIELI & C. S.P.A."', EMARKET, "3327"),
    ("AUTOSTRADE MERIDIONALI S.P.A. IN LIQUIDAZIONE", ONEINFO, "22"),
    ("ICOP S.P.A. SOCIETA' BENEFIT", EMARKET, "306512"),
    ("INTESA SANPAOLO SPA", EMARKET, "142"),
    ("A2A S.P.A.", ONEINFO, "9"),
    # Register names as listed by 1INFO / eMarket STORAGE (2026-10 snapshot).
    ('"TERNA - RETE ELETTRICA NAZIONALE SOCIETA\' PER AZIONI" (IN FORMA ABBREVIATA "TERNA S.P.A.")', [("720", "TERNA")], "720"),
    ("SANLORENZO S.P.A. IN SIGLA SL S.P.A.", [("1679", "SANLORENZO")], "1679"),
    ("RIZZOLI CORRIERE DELLA SERA MEDIAGROUP SPA O IN FORMA ABBREVIATA RCS MEDIAGROUP SPA O RCS S.P.A.",
     [("145", "RCS MEDIAGROUP"), ("146", "RIZZOLI EDITORE")], "145"),
    ("SESA S.P.A.", [("1365", "SESA"), ("1366", "SE")], "1365"),
    ("SESA S.P.A.", [("20016", "Sesa Spa")], "20016"),
])
def test_gleif_name_variants_resolve_one_register_id(legal_name, register, expected):
    assert _it_unique_register_id(legal_name, register, "test") == expected


def test_two_register_rows_with_the_same_core_are_refused():
    # eMarket STORAGE lists both "C.I.R." and "CIR": never pick one.
    with pytest.raises(GlobalProviderError):
        _it_unique_register_id("CIR S.P.A. - COMPAGNIE INDUSTRIALI RIUNITE", EMARKET, "eMarket STORAGE")


def test_variants_never_drop_business_words():
    variants = _it_name_variants("CIR S.P.A. - COMPAGNIE INDUSTRIALI RIUNITE")
    assert variants == ["CIR S.P.A. - COMPAGNIE INDUSTRIALI RIUNITE", "CIR S.P.A."]
    # A dash without a legal form before it is part of the business name.
    assert _it_name_variants("BANCA MONTE DEI PASCHI DI SIENA - BMPS") == ["BANCA MONTE DEI PASCHI DI SIENA - BMPS"]
    with pytest.raises(GlobalProviderError):
        _it_unique_register_id("DANIELI HOLDING S.P.A.", ONEINFO, "test")


class _GleifHttp:
    def __init__(self, other_names):
        self.other_names = other_names
        self.keys = []

    def cached_text(self, key, fetch):
        import json
        self.keys.append(key)
        if not key.startswith("gleif-record:"):
            raise GlobalProviderError(f"unexpected request {key}")
        names = [{"name": n, "language": "it", "type": "PREVIOUS_LEGAL_NAME"} for n in self.other_names]
        return json.dumps({"data": {"attributes": {"entity": {"otherNames": names}}}})


def test_gleif_other_names_are_a_fallback_only():
    from global_markets.oam_esef import _it_register_id
    register = [("410", "MONDO TV"), ("411", "MONDO TV FRANCE")]
    http = _GleifHttp(["MONDO TV S.P.A."])
    # 'ICC' is not a statutory qualifier: the legal name alone does not resolve.
    with pytest.raises(GlobalProviderError):
        _it_unique_register_id("MONDO TV S.P.A. ICC", register, "test")
    assert _it_register_id(http, "815600ABCDEF00000000", "MONDO TV S.P.A. ICC", register, "test") == "410"
    # A legal name that resolves on its own never consults GLEIF.
    http = _GleifHttp(["MONDO TV FRANCE S.A."])
    assert _it_register_id(http, "815600ABCDEF00000000", "MONDO TV S.P.A.", register, "test") == "410"
    assert http.keys == []


def test_other_names_cannot_resolve_an_ambiguous_register():
    from global_markets.oam_esef import _it_register_id
    register = [("1", "MONDO TV"), ("2", "MONDO TV")]
    with pytest.raises(GlobalProviderError):
        _it_register_id(_GleifHttp(["MONDO TV S.P.A."]), "815600ABCDEF00000000", "MONDO TV S.P.A. ICC", register, "test")
    # GLEIF unreachable / no otherNames: the original refusal stands.
    with pytest.raises(GlobalProviderError, match="not uniquely resolved"):
        _it_register_id(_GleifHttp([]), "815600ABCDEF00000000", "MONDO TV S.P.A. ICC", [("410", "MONDO TV")], "test")


def test_legal_form_is_stripped_only_as_a_separate_word():
    from global_markets.oam_esef import _it_name_core
    assert _it_name_core("SESA") == "SESA"
    assert _it_name_core("SESA S.P.A.") == _it_name_core("Sesa Spa") == "SESA"
    assert _it_name_core("STMICROELECTRONICS N.V.") == "STMICROELECTRONICS"
    assert _it_name_core("VINCENZO ZUCCHI - SOCIETA' PER AZIONI") == "VINCENZOZUCCHI"
    # GLEIF quotes some names whole.
    assert _it_name_core('"INTERPUMP GROUP S.P.A."') == _it_name_core("INTERPUMP GROUP") == "INTERPUMPGROUP"
    assert _it_name_core('"LU-VE - S.P.A."') == _it_name_core("LU-VE") == "LUVE"


def test_register_acronym_halves_are_a_last_resort_tier():
    from global_markets.oam_esef import _it_register_id
    igd = "IMMOBILIARE GRANDE DISTRIBUZIONE SOCIETA' DI INVESTIMENTO IMMOBIL IARE QUOTATA S.P.A. IN FORMA ABBREVIATA IGD SIIQ S.P.A."
    register = [("746", "IGD - Immobiliare Grande Distribuzione"), ("552", "SOCIETA' INIZIATIVE AUTOSTRADALI E SERVIZI - SIAS")]
    with pytest.raises(GlobalProviderError):
        _it_unique_register_id(igd, register, "test")
    assert _it_register_id(_GleifHttp([]), "815600CF8C0389D0E272", igd, register, "test") == "746"
    # An exact register name wins before any halves are considered.
    register = [("1", "TERNA"), ("2", "TERNA - ENERGY SOLUTIONS")]
    assert _it_register_id(_GleifHttp([]), "8156009E94ED54DE7C31", "TERNA S.P.A.", register, "test") == "1"
    # Halves never resolve a business name that is not in the register.
    with pytest.raises(GlobalProviderError):
        _it_register_id(_GleifHttp([]), "81560052ACB913425086", "VINCENZO ZUCCHI - SOCIETA' PER AZIONI", [("271", "ZUCCHI")], "test")


@pytest.mark.parametrize("legal_name, expected", [
    ('VALSOIA S.P.A. (IN FORMA ESTESA "VALSOIA - BONTA\' E SALUTE - S.P.A." O IN SIGLA ANCHE "V.B.S. S.P.A.")',
     {"VALSOIA S.P.A.", "VALSOIA - BONTA' E SALUTE - S.P.A.", "V.B.S. S.P.A."}),
    ("TAMBURI INVESTMENT PARTNERS S.P.A. IN VIA BREVE T.I.P. S.P.A. OV VERO TIP S.P.A.",
     {"TAMBURI INVESTMENT PARTNERS S.P.A.", "T.I.P. S.P.A.", "TIP S.P.A."}),
    ('"MOLTIPLY GROUP S.P.A.", OVVERO, IN BREVE, "MOL GROUP S.P.A." O ANCHE "GRUPPO MOL S.P.A."',
     {"MOLTIPLY GROUP S.P.A.", "MOL GROUP S.P.A.", "GRUPPO MOL S.P.A."}),
    ("INFRASTRUTTURE WIRELESS ITALIANE S.P.A. O, IN FORMA ABBREVIATA, INWIT S.P.A.",
     {"INFRASTRUTTURE WIRELESS ITALIANE S.P.A.", "INWIT S.P.A."}),
    ("CREDITO EMILIANO S.P.A. ABBREVIABILE IN CREDEMBANCA E IN CREDEM", {"CREDITO EMILIANO S.P.A.", "CREDEMBANCA", "CREDEM"}),
    ('ZIGNAGO VETRO S.P.A. CON LA SIGLA "Z.V. S.P.A."', {"ZIGNAGO VETRO S.P.A.", "Z.V. S.P.A."}),
])
def test_statutory_alias_clauses_list_every_name(legal_name, expected):
    assert expected <= set(_it_name_variants(legal_name))
