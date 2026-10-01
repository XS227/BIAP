import pytest

from global_markets.italy_issuer import FIDIA_LEI, parse_fidia_annual_text
from global_markets.providers import GlobalProviderError


SAMPLE = f"""
Fidia S.p.A. Codice LEI {FIDIA_LEI}
Relazione Finanziaria Annuale al 31 dicembre 2025
ricavi consolidati pari a 30.529 migliaia di Euro
L'EBITDA consolidato è risultato nel 2025 pari a Euro 606 migliaia
Il risultato netto consolidato registra un utile di 1.007 migliaia di Euro
Totale Attivo 26.470 28.303
Patrimonio netto del Gruppo e dei Terzi 8.056 2.957
L'indebitamento finanziario corrente al 31 dicembre 2025, pari a 1.923 migliaia di Euro
Finanziamenti a lungo termine, al netto della quota corrente 4.053 343
interessi passivi (316 migliaia di Euro)
Investimenti: pari ad 425 migliaia di Euro
A Disponibilità liquide 2.438 1.671
Risultato operativo (EBIT) (700) -2,4%
"""


def test_fidia_official_report_parser_extracts_credit_fields():
    out = parse_fidia_annual_text(SAMPLE)
    assert out["revenue"] == 30_529_000
    assert out["ebitda"] == 606_000
    assert out["net_income"] == 1_007_000
    assert out["total_assets"] == 26_470_000
    assert out["total_equity"] == 8_056_000
    assert out["total_liabilities"] == 18_414_000
    assert out["total_debt"] == 5_976_000
    assert out["interest_expense"] == 316_000
    assert out["cash_and_equivalents"] == 2_438_000


def test_fidia_parser_rejects_wrong_identity():
    with pytest.raises(GlobalProviderError):
        parse_fidia_annual_text(SAMPLE.replace(FIDIA_LEI, "WRONGLEI"))
