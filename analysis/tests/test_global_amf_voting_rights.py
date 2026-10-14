"""AMF voting-rights notices -> issuer share counts (French market)."""
from __future__ import annotations

import json
from datetime import date

import pytest

from global_markets import exchange_shares as xs
from global_markets.amf_voting_rights import (
    VotingRightsParseError, candidate_notices, fetch_latest_notice, parse_voting_rights_notice,
)
from global_markets.models import GlobalCompany

TTE_LAYOUT = """
                          TotalEnergies SE
        Informations relatives au nombre total de droits de vote et d'actions
                composant le capital social au 30 septembre 2026

                      Nombre d'actions                     Nombre de droits de vote
         Date
                     composant le capital
                                                   Théoriques (1)            Exerçables (2)
 30 septembre 2026            2 281 656 714                2 281 656 714             2 206 681 684
"""


class _Resp:
    def __init__(self, *, json_data=None, content=b""):
        self._json, self.content = json_data, content

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _Session:
    def __init__(self, rows, texts):
        self.rows, self.texts, self.headers = rows, texts, {}

    def get(self, url, params=None, **_):
        if params is not None:
            return _Resp(json_data={"results": self.rows})
        return _Resp(content=url.encode())


def _row(name, title="droits de vote", at="2026-10-06T10:00:00+00:00"):
    return {"informationdeposee_inf_dat_emt": at, "informationdeposee_inf_tit_inf": title,
            "fichierdecontenu_inf_fic_nom": name, "uin_idt_uin": name}


def test_parser_reads_dated_row():
    notice = parse_voting_rights_notice(TTE_LAYOUT)
    assert notice.shares == 2_281_656_714
    assert notice.as_of == "2026-09-30"


def test_parser_refuses_image_only_and_unrelated_text():
    with pytest.raises(VotingRightsParseError, match="no_text_layer"):
        parse_voting_rights_notice("  ")
    with pytest.raises(VotingRightsParseError, match="not_a_voting_rights_notice"):
        parse_voting_rights_notice("Annual general meeting convocation " * 10)


def test_candidate_filter_drops_buyback_reports_and_non_pdf():
    rows = [
        _row("a.pdf", "Total du nombre de droits de vote et du capital"),
        _row("b.pdf", "VINCI : Déclaration des transactions sur actions propres"),
        _row("c.xml", "droits de vote"),
        _row("d.pdf", "voting rights"),
    ]
    assert [r["fichierdecontenu_inf_fic_nom"] for r in candidate_notices(rows)] == ["a.pdf", "d.pdf"]


def test_fetch_latest_notice_skips_unparseable_then_uses_next():
    rows = [_row("bad.pdf"), _row("good.pdf")]
    session = _Session(rows, {})

    def pdf_text(content):
        if content.endswith(b"bad.pdf"):
            return "", ""
        return TTE_LAYOUT, TTE_LAYOUT

    found, status = fetch_latest_notice(session, "FR0000120271", today=date(2026, 10, 14), pdf_text=pdf_text)
    assert status == "ok" and found["shares"] == 2_281_656_714
    assert found["source_url"].endswith("good.pdf") and found["as_of"] == "2026-09-30"


def test_fetch_latest_notice_withholds_stale_and_missing():
    session = _Session([_row("good.pdf")], {})
    found, status = fetch_latest_notice(session, "FR0000120271", today=date(2028, 1, 1),
                                        pdf_text=lambda c: (TTE_LAYOUT, TTE_LAYOUT))
    assert found is None and status.startswith("stale_notice_")
    found, status = fetch_latest_notice(_Session([], {}), "FR0000120271", today=date(2026, 10, 14))
    assert (found, status) == (None, "no_notice_in_feed")


def test_refresh_records_reasons_and_lookup_applies_with_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BIAP_GLOBAL_SHARES_DIR", raising=False)
    xs._store_cache.clear()
    rows = [
        {"ticker": "TTE", "isin": "FR0000120271", "country": "FR", "exchange": "EURONEXT_PARIS", "currency": "EUR"},
        {"ticker": "NOPE", "isin": "", "country": "FR", "exchange": "EURONEXT_PARIS"},
    ]
    session = _Session([_row("good.pdf")], {})
    result = xs.refresh_amf_voting_rights(rows, "FR", "EURONEXT_PARIS", session=session, sleep=lambda s: None,
                                          pdf_text=lambda c: (TTE_LAYOUT, TTE_LAYOUT))
    assert result["stored"] == 1 and result["failed"] == {"NOPE": "no_isin"}
    stored = json.loads(open(result["path"]).read())
    assert stored["entries"]["FR:EURONEXT_PARIS:TTE"]["shares"] == 2_281_656_714

    def company(**kw):
        base = dict(ticker="TTE", name="TotalEnergies", country="FR", exchange="EURONEXT_PARIS", currency="EUR",
                    isin="FR0000120271")
        return GlobalCompany(**{**base, **kw})

    applied = xs.apply_to_company(company(net_income=15.0e9, eps=6.5))   # implies 2.31bn shares
    assert applied.shares_outstanding == 2_281_656_714
    assert applied.raw_provider_fields["exchange_share_count"]["provider"] == xs.AMF_PROVIDER

    contradicted = xs.apply_to_company(company(net_income=15.0e9, eps=60.0))  # implies 250m shares
    assert contradicted.shares_outstanding is None
    assert contradicted.raw_provider_fields["exchange_share_count"]["status"].startswith("withheld:contradicts")

    wrong_isin = xs.apply_to_company(company(isin="FR0000000000"))
    assert wrong_isin.shares_outstanding is None
