"""Portugal CMVM SDI locator: issuer matching, ESEF lodgement selection and
streaming extraction of the base64 file from the OutSystems JSON response."""
from __future__ import annotations

import base64
import io
import json

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import (
    NationalOAMESEFProvider,
    OAMHttp,
    PortugalCMVMLocator,
    _pt_name_core,
    _stream_json_base64,
)
from global_markets.providers import GlobalProviderError

ENTITIES = [
    ("226", "EDP, S.A."),
    ("71771", "EDP Renewables, SA"),
    ("63783", "Martifer - SGPS, SA"),
    ("646", "Impresa - Sociedade Gestora de Participações Soiais, S.A."),
    ("23002", "NOS, SGPS, S.A."),
]

ROWS = [
    {"ID": 11, "DATA_FACT": "2026-03-26", "DSC_FACT": "X informs Annual Report 2025 Volume 1 - non audited pdf version", "IsZip": False, "IsEN": True},
    {"ID": 12, "DATA_FACT": "2026-03-26", "DSC_FACT": "X informs Annual Report 2025 Volume 1", "IsZip": True, "IsEN": True},
    {"ID": 13, "DATA_FACT": "2026-03-26", "DSC_FACT": "X informa sobre Relatório 2025 - Versão não ESEF", "IsZip": True, "IsEN": False},
    {"ID": 14, "DATA_FACT": "2026-02-27", "DSC_FACT": "X informs FY 2025 - Individual - ESEF Version", "IsZip": True, "IsEN": True},
    {"ID": 15, "DATA_FACT": "2026-02-27", "DSC_FACT": "X informs FY 2025 - Consolidated - ESEF Version", "IsZip": True, "IsEN": True},
    {"ID": 9, "DATA_FACT": "2025-03-14", "DSC_FACT": "X informs Annual Report 2024 - ESEF Version", "IsZip": True, "IsEN": True},
]


class _Locator(PortugalCMVMLocator):
    def __init__(self, rows=ROWS):
        super().__init__(OAMHttp())
        self.rows = rows

    def _entities(self):
        return ENTITIES

    def annual_filings(self, company, lei, legal_name):
        self.http.cached_text = lambda key, fetch: json.dumps(self.rows)  # type: ignore[method-assign]
        return super().annual_filings(company, lei, legal_name)


COMPANY = GlobalCompany(country="PT", exchange="EURONEXT_LISBON", currency="EUR", ticker="EDP", name="EDP")


@pytest.mark.parametrize("name,core", [
    ("MARTIFER - S.G.P.S. S.A.", "MARTIFER"),
    ("Martifer - SGPS, SA", "MARTIFER"),
    ("IMPRESA-SOCIEDADE GESTORA DE PARTICIPAÇÕES SOCIAIS S.A.", "IMPRESA"),
    ("EDP RENEWABLES SOCIEDAD ANONIMA", "EDPRENEWABLES"),
    ("NOS, SGPS, S.A.", "NOS"),
    ("SESA", "SESA"),
])
def test_name_core_strips_stacked_legal_forms(name, core):
    assert _pt_name_core(name) == core


def test_entity_resolution_exact_and_unambiguous():
    locator = _Locator()
    assert locator._entity_id("EDP, S.A.") == "226"
    assert locator._entity_id("EDP RENEWABLES SOCIEDAD ANONIMA") == "71771"
    assert locator._entity_id("MARTIFER - S.G.P.S. S.A.") == "63783"


def test_entity_resolution_tolerates_one_register_typo_only():
    assert _Locator()._entity_id("IMPRESA-SOCIEDADE GESTORA DE PARTICIPAÇÕES SOCIAIS S.A.") == "646"
    with pytest.raises(GlobalProviderError, match="not uniquely resolved"):
        _Locator()._entity_id("GALP ENERGIA SGPS SA")


def test_filings_keep_zip_lodgements_newest_first_consolidated_preferred():
    filings = _Locator().annual_filings(COMPANY, "529900CLC3WDMGI9VH80", "EDP, S.A.")
    ids = [f.document_id.rsplit(":", 1)[1] for f in filings]
    assert ids == ["12", "15", "14", "9"]  # pdf (11) and "não ESEF" (13) skipped
    assert filings[1].scope == "consolidated" and filings[2].scope == "separate"
    assert filings[0].package_url == "cmvm-sdi:12:en"


def test_no_esef_lodgement_is_reported():
    with pytest.raises(GlobalProviderError, match="no ESEF annual financial report"):
        _Locator(rows=ROWS[:1]).annual_filings(COMPANY, "529900CLC3WDMGI9VH80", "EDP, S.A.")


def _chunks(data: bytes, size: int):
    return [data[i:i + size] for i in range(0, len(data), size)]


@pytest.mark.parametrize("size", [1, 3, 7, 64, 4096])
def test_stream_json_base64_any_chunking(size):
    payload = bytes(range(256)) * 50
    encoded = base64.b64encode(payload).decode().replace("/", "\\/")
    body = json.dumps({"data": {"DownloadFich": {"NomFich": "x.zip"}}})[:-2] + f', "Base64":"{encoded}"}}}}'
    out = io.BytesIO()
    written = _stream_json_base64(_chunks(body.encode(), size), b'"Base64":"', out, 10**7)
    assert out.getvalue() == payload and written == len(payload)


def test_stream_json_base64_limits():
    body = b'{"Base64":"' + base64.b64encode(b"x" * 1000) + b'"}'
    with pytest.raises(GlobalProviderError, match="size limit"):
        _stream_json_base64([body], b'"Base64":"', io.BytesIO(), 100)
    with pytest.raises(GlobalProviderError, match="carried no file"):
        _stream_json_base64([b'{"data":{}}'], b'"Base64":"', io.BytesIO(), 100)


def test_provider_routes_cmvm_urls_to_locator(tmp_path):
    calls = []

    class Loc(_Locator):
        def download(self, url, target, max_bytes):
            calls.append(url)
            target.write_bytes(b"PK")

    provider = NationalOAMESEFProvider(locators=[Loc()])
    provider._download("cmvm-sdi:12:en", tmp_path / "p.zip")
    assert calls == ["cmvm-sdi:12:en"]
    assert provider.supports("PT")
