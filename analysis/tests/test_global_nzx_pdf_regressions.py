"""Regressions for the NZX Ltd / Summerset annual-report PDFs.

Real-document tests use the locally archived NZX announcement PDFs and are skipped when
the files are absent (they are ~10 MB and not stored in git); the synthetic tests always run.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from global_markets import pdf_statements as ps
from global_markets.pdf_statements import PDFExtractionError, extract_primary_statements, read_pdf_pages

PDF_DIR = Path(os.environ.get("BIAP_NZX_PDF_DIR", Path.home() / "biap-global" / "pdf-real"))


def _extract(ticker: str, legal_name: str):
    path = PDF_DIR / f"{ticker}.pdf"
    if not path.exists():
        pytest.skip(f"{path} not available")
    pages = read_pdf_pages(path.read_bytes())
    return pages, extract_primary_statements(
        pages, expected_period_end="2025-12-31", expected_currency="NZD", legal_name=legal_name
    )


def test_nzx_ltd_rotated_auditor_opinion_and_statements():
    pages, result = _extract("NZX", "NZX Limited")
    assert result.audit_opinion == "unqualified" and result.audit_pages == [124]
    assert "PwC" in pages[124]  # layout mode returns '' for this page; plain fallback must read it
    values = result.values()
    assert values["revenue"] == 128_948_000.0  # note ref "8/9" must not swallow the values
    assert values["net_income"] == 21_475_000.0
    assert values["total_equity"] == 122_185_000.0
    assert values["total_assets"] == 277_389_000.0 and values["total_liabilities"] == 155_204_000.0


def test_summerset_split_label_and_equity_label():
    _, result = _extract("SUM", "Summerset Group Holdings Limited")
    assert result.audit_opinion == "unqualified" and result.audit_pages == [91]
    values = result.values()
    assert values["net_income"] == 259_720_000.0  # "Profit  for the period" printed with a double space
    assert values["total_equity"] == 3_327_862_000.0
    assert values["revenue"] == 361_774_000.0


def test_real_documents_still_fail_closed_on_wrong_period_or_issuer():
    for ticker, name in (("NZX", "NZX Limited"), ("SUM", "Summerset Group Holdings Limited")):
        pages, _ = _extract(ticker, name)
        with pytest.raises(PDFExtractionError):
            extract_primary_statements(pages, expected_period_end="2024-12-31", expected_currency="NZD", legal_name=name)
        with pytest.raises(PDFExtractionError):
            extract_primary_statements(pages, expected_period_end="2025-12-31", expected_currency="NZD", legal_name="Unrelated Holdings Limited")


# --- synthetic, always run ------------------------------------------------- #
def test_double_space_label_is_joined_but_column_gaps_are_not():
    line = "Profit  for the period" + " " * 60 + "259,720      331,958"
    chunks = ps._split_chunks(line, space_thousands=False)
    assert [c.text for c in chunks] == ["Profit for the period", "259,720", "331,958"]
    gap = "Alpha" + " " * 6 + "beta" + " " * 6 + "12"
    assert [c.text for c in ps._split_chunks(gap, space_thousands=False)] == ["Alpha", "beta", "12"]


def test_multi_note_reference_is_a_note_not_a_value():
    page = ps.PageModel.build(1, "Operating revenue" + " " * 40 + "8/9" + " " * 10 + "128,948" + " " * 8 + "120,122")
    (_, seg), = [r for r in ps.page_segments(page) if r[1].key == "operatingrevenue"]
    assert [c.value for c in seg.cells] == [None, 128948.0, 120122.0]


def test_total_equity_attributable_label_is_recognised_but_not_loose_equity_rows():
    tiers = ps.FIELD_TIERS["balance"]["total_equity"]
    assert ps._match_tier("totalequityattributabletoshareholders", tiers) == 0
    assert ps._match_tier("sharecapital", tiers) is None


def test_rotated_page_falls_back_to_plain_text_only_when_layout_is_empty():
    class Page:
        def __init__(self, layout, plain):
            self._l, self._p = layout, plain

        def extract_text(self, **kw):
            return self._l if kw.get("extraction_mode") == "layout" else self._p

    class Reader:
        is_encrypted = False

        def __init__(self, *_):
            self.pages = [Page("", "Independent auditor's report text"), Page("layout  text  here  ok", "plain")]

    import pypdf
    orig = pypdf.PdfReader
    pypdf.PdfReader = Reader
    try:
        pages = read_pdf_pages(b"%PDF-1.4 fake")
    finally:
        pypdf.PdfReader = orig
    assert pages[1] == "Independent auditor's report text"
    assert pages[2] == "layout  text  here  ok"
