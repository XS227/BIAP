from global_markets.lse_official import _gbp_price, _ordinary_row


def test_gbx_price_normalizes_to_gbp():
    assert _gbp_price(2679, "GBX") == 26.79
    assert _gbp_price(26.79, "GBP") == 26.79


def test_lse_ordinary_equity_filter_accepts_ord_share():
    assert _ordinary_row({
        "category": "EQUITY",
        "currency": "GBX",
        "isin": "GB00B1YW4409",
        "tidm": "III",
        "description": "3I GROUP PLC ORD 73 19/22P",
        "maturitydate": None,
    })


def test_lse_filter_rejects_gdr_and_non_gbp_lines():
    base = {
        "category": "EQUITY",
        "currency": "GBP",
        "isin": "GB00B1YW4409",
        "tidm": "III",
        "maturitydate": None,
    }
    assert not _ordinary_row({**base, "description": "EXAMPLE GDR EACH REPR 1 ORD"})
    assert not _ordinary_row({**base, "currency": "EUR", "description": "EXAMPLE ORD"})
