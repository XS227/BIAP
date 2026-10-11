"""iXBRL per-share facts tagged with a positive scale are issuer errors.

CIR S.p.A. FY2025 (eMarket STORAGE 181379) shows basic EPS "0,0325" with
scale="3"; taken literally that is EUR 32.50 per share. The fact is dropped,
never rescaled. Pence-denominated EPS (scale=-2) stays valid.
"""
from global_markets.ixbrl import extract_facts

_HEAD = (
    '<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body><ix:header><ix:resources>'
    '<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="http://standards.iso.org/iso/17442">5493003VOSQJSPCM0T38</xbrli:identifier></xbrli:entity>'
    '<xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
    '<xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>'
    '<xbrli:unit id="eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unitNumerator>'
    '<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>'
    '</ix:resources></ix:header>'
)


def _facts(body):
    facts, _ = extract_facts([_HEAD + body + "</body></html>"])
    return {f["dimensions"]["concept"]: float(f["value"]) for f in facts}


def test_fractional_per_share_value_in_thousands_is_dropped():
    facts = _facts(
        '<ix:nonFraction contextRef="c" name="ifrs-full:BasicEarningsLossPerShare" unitRef="eps" decimals="4" scale="3" format="ixt:num-comma-decimal">0,0325</ix:nonFraction>'
        '<ix:nonFraction contextRef="c" name="ifrs-full:ProfitLoss" unitRef="eur" decimals="-3" scale="3" format="ixt:num-dot-decimal">49,254</ix:nonFraction>'
    )
    assert "ifrs-full:BasicEarningsLossPerShare" not in facts
    assert facts["ifrs-full:ProfitLoss"] == 49_254_000


def test_pence_and_unscaled_per_share_values_are_kept():
    facts = _facts(
        '<ix:nonFraction contextRef="c" name="ifrs-full:BasicEarningsLossPerShare" unitRef="eps" decimals="3" scale="-2">12.3</ix:nonFraction>'
        '<ix:nonFraction contextRef="c" name="ifrs-full:DilutedEarningsLossPerShare" unitRef="eps" decimals="2">1.25</ix:nonFraction>'
    )
    assert round(facts["ifrs-full:BasicEarningsLossPerShare"], 6) == 0.123
    assert facts["ifrs-full:DilutedEarningsLossPerShare"] == 1.25


def test_decimal_per_share_value_in_thousands_is_dropped():
    # Logista FY2025 (CNMV IFA): EPS "2,13" tagged scale="3".
    facts = _facts(
        '<ix:nonFraction contextRef="c" name="ifrs-full:BasicEarningsLossPerShare" unitRef="eps" decimals="2" scale="3" format="ixt:num-comma-decimal">2,13</ix:nonFraction>'
    )
    assert "ifrs-full:BasicEarningsLossPerShare" not in facts
