"""Netherlands AFM register locator: issuer matching on legal name and
ESEF-only annual lodgements, newest first."""
from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.oam_esef import NationalOAMESEFProvider, NetherlandsAFMLocator, OAMHttp
from global_markets.providers import GlobalProviderError

ROWS = [
    {"id": "A2510-03613", "datum": "2/11/2026 12:35:22 PM", "uitgevende-instelling": "Heineken N.V.", "boekjaar": "2025", "filename": "heia-2025-12-31-en-A2510-03613.xbri"},
    {"id": "A2510-03612", "datum": "2/11/2026 7:41:34 AM", "uitgevende-instelling": "Heineken Holding N.V.", "boekjaar": "2025", "filename": "heiho-2025-12-31-1-en-A2510-03612.xbri"},
    {"id": "A2402-07210", "datum": "2/20/2025 12:07:13 PM", "uitgevende-instelling": "Heineken N.V.", "boekjaar": "2024", "filename": "heia-2024-12-31-en-A2402-07210.zip"},
]


class _Locator(NetherlandsAFMLocator):
    def __init__(self):
        super().__init__(OAMHttp())

    def _register(self):
        return ROWS


COMPANY = GlobalCompany(country="NL", exchange="EURONEXT_AMSTERDAM", currency="EUR", ticker="HEIA", name="HEINEKEN", isin="NL0000009165")


def test_exact_issuer_only_newest_first():
    filings = _Locator().annual_filings(COMPANY, "724500K5PNBYIOQRUL45", "Heineken N.V.")
    assert [f.document_id for f in filings] == ["AFM:A2510-03613", "AFM:A2402-07210"]
    assert filings[0].package_url == "afm-register:A2510-03613"
    assert filings[0].published_at == "2026-02-11"
    holding = _Locator().annual_filings(COMPANY, "x", "HEINEKEN HOLDING N.V.")
    assert [f.document_id for f in holding] == ["AFM:A2510-03612"]


def test_unknown_issuer_is_not_guessed():
    with pytest.raises(GlobalProviderError, match="not uniquely resolved"):
        _Locator().annual_filings(COMPANY, "x", "ArcelorMittal")


def test_netherlands_is_served_by_national_oam_provider():
    assert NationalOAMESEFProvider().supports("NL")
