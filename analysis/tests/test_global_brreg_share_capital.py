"""Norwegian share counts from Enhetsregisteret, identity via GLEIF (no name matching)."""
from __future__ import annotations

import json

from global_markets import exchange_shares as xs
from global_markets.brreg_share_capital import orgnr_from_gleif, share_capital_from_brreg
from global_markets.models import GlobalCompany


def _gleif(lei="OW6OFBNCKXC4US5C7523", name="EQUINOR ASA", reg="923 609 016", at="RA000472", status="ACTIVE", n=1):
    row = {"id": lei, "attributes": {"entity": {"legalName": {"name": name}, "registeredAs": reg,
                                                 "registeredAt": {"id": at}, "status": status},
                                     "registration": {"status": "ISSUED"}}}
    return {"data": [row] * n}


def _brreg(**kw):
    base = {"organisasjonsnummer": "923609016", "navn": "EQUINOR ASA", "organisasjonsform": {"kode": "ASA"},
            "kapital": {"antallAksjer": 2390749040, "belop": 5976872600.0, "innfortDato": "2026-07-02",
                        "type": "Aksjekapital", "valuta": "NOK"}}
    base.update(kw)
    return base


def test_orgnr_from_gleif_accepts_both_norwegian_registry_ids():
    for at in ("RA000472", "RA000473"):
        found, status = orgnr_from_gleif(_gleif(at=at))
        assert status == "ok" and found["orgnr"] == "923609016"


def test_orgnr_refuses_foreign_register_ambiguity_and_inactive():
    assert orgnr_from_gleif(_gleif(at="RA000544"))[1].startswith("not_norwegian_register")
    assert orgnr_from_gleif(_gleif(n=2))[1] == "gleif_ambiguous_2"
    assert orgnr_from_gleif(_gleif(status="INACTIVE"))[1] == "gleif_no_active_record"
    assert orgnr_from_gleif(_gleif(reg=""))[1] == "gleif_no_orgnr"


def test_share_capital_parsing_and_refusals():
    ok, status = share_capital_from_brreg(_brreg(), "923609016", "EQUINOR ASA")
    assert status == "ok" and ok["shares"] == 2_390_749_040 and ok["as_of"] == "2026-07-02"
    assert share_capital_from_brreg(_brreg(), "111111111")[1] == "brreg_identity_mismatch"
    assert share_capital_from_brreg(_brreg(), "923609016", "OTHER ASA")[1] == "brreg_name_mismatch"
    assert share_capital_from_brreg(_brreg(organisasjonsform={"kode": "ENK"}), "923609016")[1] == "brreg_form_ENK"
    assert share_capital_from_brreg(_brreg(kapital={}), "923609016")[1] == "brreg_no_capital"
    usd = _brreg()
    usd["kapital"] = {**usd["kapital"], "valuta": "USD"}
    assert share_capital_from_brreg(usd, "923609016")[1].startswith("brreg_capital_currency")
    assert share_capital_from_brreg(_brreg(konkurs=True), "923609016")[1] == "brreg_not_active"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._d


class _Session:
    def __init__(self, gleif_by_isin, brreg_by_org):
        self.g, self.b = gleif_by_isin, brreg_by_org

    def get(self, url, params=None, **_):
        if "gleif" in url:
            return _Resp(self.g[params["filter[isin]"]])
        return _Resp(self.b[url.rsplit("/", 1)[-1]])


def test_refresh_and_apply_with_net_income_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BIAP_GLOBAL_SHARES_DIR", raising=False)
    xs._store_cache.clear()
    rows = [{"ticker": "EQNR", "isin": "NO0010096985", "country": "NO", "exchange": "EURONEXT_OSLO", "currency": "NOK"},
            {"ticker": "SUBC", "isin": "NO0010735343", "country": "NO", "exchange": "EURONEXT_OSLO", "currency": "NOK"}]
    session = _Session({"NO0010096985": _gleif(), "NO0010735343": _gleif(at="RA000544", name="SUBSEA 7 SA")},
                       {"923609016": _brreg()})
    result = xs.refresh_brreg_share_capital(rows, "NO", "EURONEXT_OSLO", session=session, sleep=lambda s: None)
    assert result["stored"] == 1 and result["failed"]["SUBC"].startswith("not_norwegian_register")
    assert json.loads(open(result["path"]).read())["entries"]["NO:EURONEXT_OSLO:EQNR"]["orgnr"] == "923609016"

    def company(**kw):
        return GlobalCompany(**{**dict(ticker="EQNR", name="Equinor", country="NO", exchange="EURONEXT_OSLO",
                                       currency="NOK", isin="NO0010096985"), **kw})

    ok = xs.apply_to_company(company(net_income=7.4e10, eps=30.0))     # implies 2.47bn shares
    assert ok.shares_outstanding == 2_390_749_040
    assert ok.raw_provider_fields["exchange_share_count"]["provider"] == xs.BRREG_PROVIDER
    bad = xs.apply_to_company(company(net_income=7.4e10, eps=300.0))   # implies 247m shares
    assert bad.shares_outstanding is None
