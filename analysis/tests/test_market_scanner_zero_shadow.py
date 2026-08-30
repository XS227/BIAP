from market_scanner import _bulk_candidate


def test_compact_fields_win_over_zero_legacy_fields():
    raw = {
        "insCode": "52724381011699987",
        "lva": "ضهرم6040",
        "lvc": "اختيارخ اهرم-26000-1405/06/25",
        "pdv": 33110.0,
        "pcl": 33006.0,
        "py": 32346.0,
        "qtj": 425.0,
        "qtc": 14027608000.0,
        "ztt": 53.0,
        "pDrCotVal": 0.0,
        "pClosing": 0.0,
        "qTotTran5J": 0.0,
        "qTotCap": 0.0,
        "zTotTran": 0.0,
    }
    candidate = _bulk_candidate(raw)
    assert candidate is not None
    assert candidate.symbol == "ضهرم6040"
    assert candidate.last_price == 33110.0
    assert candidate.closing_price == 33006.0
    assert candidate.yesterday_price == 32346.0
    assert candidate.volume == 425.0
    assert candidate.trade_value == 14027608000.0
    assert candidate.trade_count == 53.0
