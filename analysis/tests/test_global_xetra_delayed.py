import gzip
import io
import json

from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany
from global_markets.xetra_delayed import (
    DeutscheBoerseXetraDelayedClient,
    aggregate_xetra_posttrade,
)


def _company(ticker, isin):
    return GlobalCompany(
        country="DE",
        exchange="XETRA",
        currency="EUR",
        ticker=ticker,
        name=ticker,
        mic_code="XETR",
        isin=isin,
        instrument_type="Common Stock",
    )


def _gzip_rows(rows):
    raw=b"".join((json.dumps(row)+"\n").encode("utf-8") for row in rows)
    return gzip.compress(raw)


def test_xetra_posttrade_aggregates_latest_price_and_turnover():
    rows=[
        {
            "instrumentIdentificationCode":"DE0007164600",
            "priceCurrency":"EUR",
            "price":180.0,
            "quantity":10,
            "tradingDateAndTime":"2026-09-24T08:00:00Z",
            "mmtModificationInd":"-",
            "venueOfExecution":"XETA",
        },
        {
            "instrumentIdentificationCode":"DE0007164600",
            "priceCurrency":"EUR",
            "price":184.12,
            "quantity":5,
            "tradingDateAndTime":"2026-09-24T19:53:13Z",
            "mmtModificationInd":"-",
            "venueOfExecution":"XETA",
        },
        {
            "instrumentIdentificationCode":"DE0008404005",
            "priceCurrency":"EUR",
            "price":419.7,
            "quantity":2,
            "tradingDateAndTime":"2026-09-24T19:47:40Z",
            "mmtModificationInd":"-",
            "venueOfExecution":"XETA",
        },
    ]
    stats=aggregate_xetra_posttrade(
        _gzip_rows(rows),
        [_company("SAP","DE0007164600"),_company("ALV","DE0008404005")],
    )
    assert stats["DE0007164600"]["lastPrice"] == 184.12
    assert stats["DE0007164600"]["volume"] == 15
    assert stats["DE0007164600"]["turnover"] == 1800 + 920.6
    assert stats["DE0007164600"]["trades"] == 2


def test_xetra_posttrade_does_not_add_modified_trade_to_volume():
    rows=[
        {
            "instrumentIdentificationCode":"DE0007164600",
            "priceCurrency":"EUR",
            "price":184.0,
            "quantity":100,
            "tradingDateAndTime":"2026-09-24T10:00:00Z",
            "mmtModificationInd":"-",
        },
        {
            "instrumentIdentificationCode":"DE0007164600",
            "priceCurrency":"EUR",
            "price":185.0,
            "quantity":100,
            "tradingDateAndTime":"2026-09-24T11:00:00Z",
            "mmtModificationInd":"C",
        },
    ]
    stats=aggregate_xetra_posttrade(_gzip_rows(rows),[_company("SAP","DE0007164600")])
    assert stats["DE0007164600"]["volume"] == 100
    assert stats["DE0007164600"]["lastPrice"] == 184.0


def test_xetra_client_builds_stage_one_quotes(monkeypatch):
    client=DeutscheBoerseXetraDelayedClient()
    content=_gzip_rows([
        {
            "instrumentIdentificationCode":"DE0007164600",
            "priceCurrency":"EUR",
            "price":184.12,
            "quantity":50,
            "tradingDateAndTime":"2026-09-24T19:53:13Z",
            "mmtModificationInd":"-",
            "venueOfExecution":"XETA",
        }
    ])
    monkeypatch.setattr(
        client,
        "_download_daily",
        lambda: ("2026-09-24","https://mfs.deutsche-boerse.com/api/download/test.json.gz",content),
    )
    quotes,errors,source=client.batch_quotes(
        [_company("SAP","DE0007164600")],
        "DE",
        get_exchange("DE","XETRA"),
    )
    assert errors == []
    assert quotes[0]["ticker"] == "SAP"
    assert quotes[0]["price"] == 184.12
    assert quotes[0]["averageVolume"] == 50
    assert quotes[0]["provider"] == "official-deutsche-boerse-xetra-delayed-posttrade"
    assert quotes[0]["quoteDate"] == "2026-09-24"
    assert "official Xetra delayed post-trade" in source


def test_xetra_delayed_support_is_strict():
    assert DeutscheBoerseXetraDelayedClient.supported("DE","XETRA")
    assert not DeutscheBoerseXetraDelayedClient.supported("DE","FRANKFURT")
    assert not DeutscheBoerseXetraDelayedClient.supported("GB","LSE")
