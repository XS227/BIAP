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


def _row(tidm, isin, desc):
    return {"category": "EQUITY", "currency": "GBX", "isin": isin, "tidm": tidm, "description": desc,
            "name": "ORD", "issuername": desc.split(" ORD")[0], "maturitydate": None}


def _client_with(rows, icb, failures=0):
    from global_markets.lse_official import LSEOfficialClient
    client = LSEOfficialClient()
    client._component_id = lambda session: "c"
    client._page = lambda session, cid, page, sector=None: {"content": rows, "totalPages": 1, "totalElements": len(rows)}
    client._icb_sector_map = lambda session, cid: icb
    return client


def test_pooled_investment_vehicles_are_excluded_by_lse_icb_not_by_name():
    from global_markets.lse_official import pooled_investment_icb
    rows = [
        _row("III", "GB00B1YW4409", "3I GROUP PLC ORD 73 19/22P"),
        _row("WTAN", "GB00BJVDZ946", "WITAN INVESTMENT TRUST PLC ORD 1P"),
        _row("AAIF", "GB00BDFX7R03", "ABRDN ASIA FOCUS PLC ORD 25P"),
        _row("BARC", "GB0031348658", "BARCLAYS PLC ORD 25P"),
    ]
    icb = {
        ("GB00B1YW4409", "III"): ("302020", "Investment Banking and Brokerage Services"),
        ("GB00BJVDZ946", "WTAN"): ("302040", "Closed End Investments"),
        ("GB00BDFX7R03", "AAIF"): ("302050", "Open End and Miscellaneous Investment Vehicles"),
        ("GB0031348658", "BARC"): ("301010", "Banks"),
    }
    client = _client_with(rows, icb)
    _, kept, meta = client.eligible_rows()
    assert sorted(r["tidm"] for r in kept) == ["BARC", "III"]
    assert {r["tidm"]: r["icbSector"] for r in kept}["BARC"] == "Banks"
    assert meta["excludedPooledInvestmentVehicles"] == 2 and meta["icbClassifiedCount"] == 4
    # an operating Investment Banking company is NOT a pooled vehicle
    assert not pooled_investment_icb("302020") and pooled_investment_icb("302040")


def test_icb_outage_never_hides_a_company():
    rows = [_row("WTAN", "GB00BJVDZ946", "WITAN INVESTMENT TRUST PLC ORD 1P")]
    client = _client_with(rows, {})
    _, kept, meta = client.eligible_rows()
    assert [r["tidm"] for r in kept] == ["WTAN"]
    assert meta["excludedPooledInvestmentVehicles"] == 0 and meta["icbClassifiedCount"] == 0


def test_uk_company_carries_icb_industry_as_sector_and_icb_sector_as_industry():
    from global_markets.lse_official import LSEOfficialUniverseProvider
    rows = [_row("BARC", "GB0031348658", "BARCLAYS PLC ORD 25P")]
    icb = {("GB0031348658", "BARC"): ("301010", "Banks")}
    provider = LSEOfficialUniverseProvider()
    provider.client = _client_with(rows, icb)
    company = provider.list_instruments(country="GB", exchange="LSE")[0]
    assert (company.sector, company.industry) == ("Financials", "Banks")
    assert company.raw_provider_fields["lse_icb_code"] == "301010"
