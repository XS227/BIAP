"""Italian authorized-storage (SDIR) ESEF coverage: 1INFO + eMarket STORAGE.

Regression for ISP / ERG / BPE resolving to stale FY2022/FY2024 filings because
only 1INFO was queried, and for A2A whose 1INFO package embeds a subsidiary LEI.
"""
from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import (
    ItalyEMarketStorageLocator,
    ItalySDIRLocator,
    NationalOAMESEFProvider,
    OAMFiling,
    OAMLocator,
)
from global_markets.providers import GlobalProviderError

BPER_LEI = "N747OI7JINV7RUUH6190"
A2A_LEI = "81560076E3944316DB24"
A2A_ENERGIA_LEI = "815600B7FD80E48C1896"

ISSUERS_HTML = """
<select data-drupal-selector="edit-azienda" id="edit-azienda" name="azienda">
<option value="" selected="selected">Emittente/Regulator</option>
<option value="1095">BPER BANCA</option>
<option value="142">INTESA SANPAOLO</option>
<option value="5825">ERG</option>
<option value="131655">ERGYCAPITAL</option>
</select>
"""


def _row(protocol, issuer, stamp, href, title):
    return (
        f'<div class="views-row"><div class="views-field views-field-nothing"><span class="field-content">'
        f'<div class="azienda-wrapper" data-protocollo="{protocol}">'
        f'<div class="news-logo"><a href="/it/comunicati-finanziari?azienda={issuer}"><img src="/x.jpg"></a></div>'
        f'<div class="news-data"><a href=""><time datetime="1Z" class="datetime">{stamp}</time></a></div>'
        f'<div class="news-azienda"><a href="{href}">X</a></div></div>'
        f'<div class="news-title"><a href="{href}" target="_blank">{title}</a></div></span></div></div>'
    )


BPER_ANNUAL_HTML = "".join([
    _row(181097, 1095, "01/04/2026 - 19:05", "/sites/default/files/comunicati/2026-04/20260401_181097.pdf",
         "Progetto di Bilancio d'Esercizio 2025 BPER"),
    _row(181096, 1095, "01/04/2026 - 18:57", "/sites/default/files/xbrl/2026-04/20260401_181096.zip",
         '<span class="icon-esef" title="ESEF"></span>Progetto di Bilancio d&#039;Esercizio 2025 BPER (xHTML)'),
    _row(181088, 1095, "01/04/2026 - 18:24", "/sites/default/files/xbrl/2026-04/20260401_181088.zip",
         '<span class="icon-esef"></span>Resoconti dell’esercizio 2025 Banca Popolare di Sondrio S.p.A. (ESEF)'),
    _row(181086, 1095, "01/04/2026 - 18:03", "/sites/default/files/xbrl/2026-04/20260401_181086.xbri",
         '<span class="icon-esef"></span>Bilancio Consolidato 2025 BPER (ESEF)'),
    _row(163173, 1095, "27/03/2025 - 17:50", "/sites/default/files/xbrl/2025-03/20250327_163173.zip",
         '<span class="icon-esef"></span>Bilancio Consolidato 2024'),
    # A row attributed to another issuer must never be attached to BPER.
    _row(999, 142, "02/04/2026 - 10:00", "/sites/default/files/xbrl/2026-04/x.zip", "Bilancio consolidato 2025"),
])


class _Http:
    def __init__(self, pages):
        self.pages = pages
        self.keys = []

    def cached_text(self, key, fetch):
        self.keys.append(key)
        if key not in self.pages:
            raise GlobalProviderError(f"unexpected request {key}")
        return self.pages[key]


def _company(ticker="BPE", name="BPER BANCA", isin="IT0000066123"):
    return GlobalCompany(country="IT", exchange="EURONEXT_MILAN", currency="EUR", ticker=ticker, name=name, isin=isin)


def _emarket():
    return ItalyEMarketStorageLocator(_Http({"emarket:issuers": ISSUERS_HTML, "emarket:annual:1095": BPER_ANNUAL_HTML}))


def test_emarket_lists_only_esef_packages_of_the_resolved_issuer():
    filings = _emarket().annual_filings(_company(), BPER_LEI, "BPER BANCA S.P.A.")
    ids = [f.document_id for f in filings]
    assert "EMARKET-STORAGE:181097" not in ids  # PDF is never ESEF
    assert "EMARKET-STORAGE:999" not in ids  # other issuer's row
    assert set(ids) == {"EMARKET-STORAGE:181096", "EMARKET-STORAGE:181088", "EMARKET-STORAGE:181086", "EMARKET-STORAGE:163173"}
    consolidated = next(f for f in filings if f.document_id == "EMARKET-STORAGE:181086")
    assert consolidated.package_url == "https://www.emarketstorage.it/sites/default/files/xbrl/2026-04/20260401_181086.xbri"
    assert consolidated.scope == "consolidated"
    assert consolidated.published_at == "2026-04-01T18:03:00+02:00"
    assert next(f for f in filings if f.document_id == "EMARKET-STORAGE:181096").scope == "separate"


@pytest.mark.parametrize("title,scope", [
    ("Relazione e Bilancio consolidato del Gruppo Enel al 31 dicembre 2025", "consolidated"),
    ("Relazione e Bilancio di esercizio di Enel S.p.A. al 31 dicembre 2025", "separate"),
    ("Progetto di Bilancio d'Esercizio 2025 BPER (xHTML)", "separate"),
    ("Relazione finanziaria annuale al 31/12/25 (formato ESEF)", None),
])
def test_italian_storage_title_scope(title, scope):
    from global_markets.oam_esef import _it_title_scope
    assert _it_title_scope(title) == scope


def test_emarket_issuer_identity_must_be_unique_and_exact():
    locator = _emarket()
    assert locator._issuer_id("ERG S.P.A.") == "5825"  # not ERGYCAPITAL
    with pytest.raises(GlobalProviderError, match="not uniquely resolved"):
        locator._issuer_id("A2A S.P.A.")


def test_sdir_merges_storages_and_ranks_consolidated_current_cycle_first():
    class _Stale1Info(OAMLocator):
        oam = "it-1info"
        country = "IT"

        def annual_filings(self, company, lei, legal_name):
            return [OAMFiling(oam=self.oam, document_id="1INFO:138041_oneinfo.zip", package_url="u", landing_url="l",
                              published_at="2024-03-28T19:00:00+00:00", label="Relazione integrata e bilancio consolidato al 31/12/2023",
                              scope="consolidated")]

    locator = ItalySDIRLocator(None)
    locator.storages = [_Stale1Info(None), _emarket()]
    filings = locator.annual_filings(_company(), BPER_LEI, "BPER BANCA S.P.A.")
    assert filings[0].document_id == "EMARKET-STORAGE:181086"
    assert filings[-1].document_id == "1INFO:138041_oneinfo.zip"


def test_sdir_reports_every_storage_gap_when_nothing_is_listed():
    class _Empty(OAMLocator):
        country = "IT"

        def __init__(self, oam):
            self.oam = oam

        def annual_filings(self, company, lei, legal_name):
            raise GlobalProviderError("lists no annual ESEF package")

    locator = ItalySDIRLocator(None)
    locator.storages = [_Empty("it-1info"), _Empty("it-emarket-storage")]
    with pytest.raises(GlobalProviderError, match="it-1info: .*it-emarket-storage: "):
        locator.annual_filings(_company(), BPER_LEI, "BPER BANCA S.P.A.")


class _Fixed(OAMLocator):
    oam = "it-sdir"
    country = "IT"

    def __init__(self, filings):
        self.filings = filings

    def annual_filings(self, company, lei, legal_name):
        return self.filings


def _annual_facts(lei, year=2025):
    period = f"{year}-01-01/{year}-12-31"
    return {
        "entities": [lei],
        "facts": [
            {"dimensions": {"concept": "ifrs-full:ProfitLoss", "entity": lei, "period": period, "unit": "iso4217:EUR"}, "value": 782e6},
            {"dimensions": {"concept": "ifrs-full:Revenue", "entity": lei, "period": period, "unit": "iso4217:EUR"}, "value": 14063e6},
        ],
    }


def test_a2a_package_with_subsidiary_lei_is_never_promoted(monkeypatch):
    filing = OAMFiling(oam="it-1info", document_id="1INFO:166284_oneinfo.zip", package_url="u", landing_url="l",
                       published_at="2026-04-17T09:59:16+00:00", scope="consolidated")
    provider = NationalOAMESEFProvider(locators=[_Fixed([filing])])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (A2A_LEI, "A2A S.P.A."))
    monkeypatch.setattr(provider, "package_facts", lambda f: _annual_facts(A2A_ENERGIA_LEI))
    with pytest.raises(GlobalProviderError, match=f"report entity \\['{A2A_ENERGIA_LEI}'\\] != LEI {A2A_LEI}"):
        provider.enrich_fundamentals(_company("A2A", "A2A", "IT0001233417"))


def test_matching_lei_fy2025_package_is_official_with_scope(monkeypatch):
    mismatched = OAMFiling(oam="it-emarket-storage", document_id="EMARKET-STORAGE:181088", package_url="u", landing_url="l",
                           published_at="2026-04-01T18:24:00+02:00", scope="separate")
    good = OAMFiling(oam="it-emarket-storage", document_id="EMARKET-STORAGE:181086", package_url="u", landing_url="l",
                     published_at="2026-04-01T18:03:00+02:00", scope="consolidated")
    provider = NationalOAMESEFProvider(locators=[_Fixed([mismatched, good])])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (BPER_LEI, "BPER BANCA S.P.A."))
    monkeypatch.setattr(provider, "package_facts", lambda f: _annual_facts("8156000C2FB5A2A7DD49" if f is mismatched else BPER_LEI))
    result = provider.enrich_fundamentals(_company())
    assert result.filing_period_end == "2025-12-31"
    assert result.report_scope == "consolidated"
    assert result.raw_provider_fields["oam_document_id"] == "EMARKET-STORAGE:181086"
    assert result.raw_provider_fields["oam_entity_lei_verified"] is True
    source = result.sources[-1]
    assert source.provider == "official-oam-it-emarket-storage"
    assert source.source_type == "official_regulatory_xbrl"


IFIS_ISSUERS_HTML = '<select id="edit-azienda" name="azienda"><option value="1603">BANCA IFIS</option></select>'
IFIS_ANNUAL_HTML = _row(144925, 1603, "27/03/2024 - 18:40", "/sites/default/files/xbrl/2024-03/20240327_144925.zip", "Annual Report 2023")
IFIS_REGEM_HTML = "".join([
    _row(180051, 1603, "26/03/2026 - 12:02", "/sites/default/files/comunicati/2026-03/20260326_180051.pdf", "Banca Ifis S.p.A.: Bilancio 2025"),
    _row(180050, 1603, "26/03/2026 - 11:59", "/sites/default/files/xbrl/2026-03/20260326_180050.zip", "Banca Ifis S.p.A.: Bilancio 2025"),
    _row(180055, 1603, "26/03/2026 - 12:05", "/sites/default/files/comunicati/2026-03/20260326_180055.pdf", "Banca Ifis S.p.A.: Pillar III"),
    # The same protocol listed twice is one candidate.
    _row(144925, 1603, "27/03/2024 - 18:40", "/sites/default/files/xbrl/2024-03/20240327_144925.zip", "Annual Report 2023"),
])


def test_emarket_regem_category_esef_packages_are_candidates():
    # Banca IFIS lodged its FY2025 ESEF package under REGEM (category 150).
    http = _Http({"emarket:issuers": IFIS_ISSUERS_HTML, "emarket:annual:1603": IFIS_ANNUAL_HTML, "emarket:regem:1603": IFIS_REGEM_HTML})
    filings = ItalyEMarketStorageLocator(http).annual_filings(_company("IF", "BANCA IFIS", "IT0003188064"), "8156005420362AE59184", "BANCA IFIS S.P.A.")
    assert [f.document_id for f in filings] == ["EMARKET-STORAGE:180050", "EMARKET-STORAGE:144925"]  # PDFs never
    assert filings[0].landing_url.endswith("categoria=150&azienda=1603")
    assert filings[1].landing_url.endswith("categoria=100&azienda=1603")


def test_emarket_regem_outage_keeps_category_1_1_listing():
    http = _Http({"emarket:issuers": IFIS_ISSUERS_HTML, "emarket:annual:1603": IFIS_ANNUAL_HTML})
    filings = ItalyEMarketStorageLocator(http).annual_filings(_company("IF", "BANCA IFIS", "IT0003188064"), "8156005420362AE59184", "BANCA IFIS S.P.A.")
    assert [f.document_id for f in filings] == ["EMARKET-STORAGE:144925"]


def test_1info_accepts_xbri_report_packages():
    # Banca Sistema FY2025: 1INFO protocolCodeXbrl '165391_oneinfo.xbri'.
    import json
    from global_markets.oam_esef import Italy1InfoLocator

    def row(stored, exercise, xbrl, title):
        return {"ndg": 1738, "dataStoccaggio": stored, "dataEsercizio": exercise, "protocolCodeXbrl": xbrl,
                "oggetto": title, "bilancio_consolidato": None}

    rows = [
        row(1774972800, 1767139200, None, "Fascicolo di Bilancio al 31 dicembre 2025"),
        row(1774972800, 1767139200, "165391_oneinfo.xbri", "Bilancio al 31 dicembre 2025 (formato ESEF)"),
        row(1711670400, 1703980800, "138317_oneinfo.zip", "BILANCIO CONSOLIDATO AL 31 DICEMBRE 2023"),
        row(1711670400, 1703980800, "138318_oneinfo.pdf", "BILANCIO 2023"),
    ]
    http = _Http({
        "1info:companies": json.dumps([{"ndg": 1738, "descrizione": "Banca Sistema S.p.A."}]),
        "1info:annual:1738": json.dumps({"data": rows}),
    })
    filings = Italy1InfoLocator(http).annual_filings(_company("BST", "BANCA SISTEMA", "IT0003211601"), "815600B5C61A10BBB451", "BANCA SISTEMA S.P.A.")
    assert [f.document_id for f in filings] == ["1INFO:165391_oneinfo.xbri", "1INFO:138317_oneinfo.zip"]
    assert "file=165391_oneinfo.xbri" in filings[0].package_url and "year=2025" in filings[0].package_url
