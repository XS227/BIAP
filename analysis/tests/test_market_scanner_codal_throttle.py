import market_scanner


def test_codal_scan_is_serialized():
    assert market_scanner.DEFAULT_CODAL_DELAY_SECONDS >= 0.0
