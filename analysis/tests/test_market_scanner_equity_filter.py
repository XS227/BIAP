from market_scanner import _bulk_candidate


def _row(**overrides):
    row = {
        "insCode": "46348559193224090",
        "insID": "IRO1FOLD0001",
        "lva": "فولاد",
        "lvc": "فولاد مبارکه اصفهان",
        "pdv": 4100.0,
        "pcl": 4080.0,
        "py": 4000.0,
        "qtj": 10_000_000.0,
        "qtc": 41_000_000_000.0,
        "ztt": 1200.0,
    }
    row.update(overrides)
    return row


def test_keeps_ordinary_iro1_share():
    item = _bulk_candidate(_row())
    assert item is not None
    assert item.symbol == "فولاد"


def test_rejects_option_even_with_trading_activity():
    assert _bulk_candidate(_row(insID="IRO9AHRM0C21", lva="ضهرم6040", lvc="اختيارخ اهرم-26000-1405/06/25")) is None


def test_rejects_rights_symbol():
    assert _bulk_candidate(_row(lva="ومعادنح", lvc="ح . توسعه‌معادن‌وفلزات‌")) is None


def test_rejects_fund_by_name():
    assert _bulk_candidate(_row(lva="نمونه", lvc="صندوق سرمایه گذاری نمونه")) is None
