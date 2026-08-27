from unittest.mock import patch

import audit_parser
import codal_pdf_cache
import related_party
from codal_data import CodalFiling


def _filing(tracing_no="TN-1", pdf_url="/reports/filing.pdf"):
    return CodalFiling(
        tracing_no=tracing_no,
        title="test filing",
        sent_at=None,
        publish_at=None,
        letter_code=None,
        url=None,
        pdf_url=pdf_url,
        excel_url=None,
        attachment_url=None,
    )


def _use_isolated_cache(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "codal_pdf_text_cache.json")
    monkeypatch.setattr(codal_pdf_cache, "DEFAULT_CACHE_PATH", cache_path)
    monkeypatch.setattr(codal_pdf_cache, "_memory_cache", None)
    return cache_path


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def _fake_pdftotext(cmd, **kwargs):
    txt_path = cmd[3]
    with open(txt_path, "w", encoding="utf-8") as handle:
        handle.write("extracted pdf text")
    return None


def test_filing_without_pdf_url_returns_none_without_network(tmp_path, monkeypatch):
    _use_isolated_cache(tmp_path, monkeypatch)
    with patch("codal_pdf_cache.urlopen") as mock_urlopen:
        result = codal_pdf_cache.extracted_text_for_filing(
            _filing(pdf_url=None), www_base="https://www.codal.ir/"
        )
    assert result is None
    mock_urlopen.assert_not_called()


def test_successful_extraction_is_cached_and_not_refetched(tmp_path, monkeypatch):
    _use_isolated_cache(tmp_path, monkeypatch)
    filing = _filing()

    with patch("codal_pdf_cache.urlopen", return_value=_FakeResponse(b"%PDF-fake")) as mock_urlopen, \
         patch("codal_pdf_cache.subprocess.run", side_effect=_fake_pdftotext) as mock_run:
        first = codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")
        second = codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")

    assert first == "extracted pdf text"
    assert second == "extracted pdf text"
    mock_urlopen.assert_called_once()
    mock_run.assert_called_once()


def test_cache_survives_a_fresh_process_via_disk_persistence(tmp_path, monkeypatch):
    cache_path = _use_isolated_cache(tmp_path, monkeypatch)
    filing = _filing()

    with patch("codal_pdf_cache.urlopen", return_value=_FakeResponse(b"%PDF-fake")), \
         patch("codal_pdf_cache.subprocess.run", side_effect=_fake_pdftotext):
        codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")

    # Simulate a fresh process: drop the in-memory cache but keep the same
    # on-disk file (this is what actually happens across a biap-fin restart).
    monkeypatch.setattr(codal_pdf_cache, "_memory_cache", None)
    monkeypatch.setattr(codal_pdf_cache, "DEFAULT_CACHE_PATH", cache_path)

    with patch("codal_pdf_cache.urlopen") as mock_urlopen:
        result = codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")

    assert result == "extracted pdf text"
    mock_urlopen.assert_not_called()


def test_download_failure_is_never_cached(tmp_path, monkeypatch):
    _use_isolated_cache(tmp_path, monkeypatch)
    filing = _filing()

    with patch("codal_pdf_cache.urlopen", side_effect=OSError("boom")) as mock_urlopen:
        first = codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")
        second = codal_pdf_cache.extracted_text_for_filing(filing, www_base="https://www.codal.ir/")

    assert first is None
    assert second is None
    assert mock_urlopen.call_count == 2


def test_different_filings_do_not_collide_in_the_cache(tmp_path, monkeypatch):
    _use_isolated_cache(tmp_path, monkeypatch)
    filing_a = _filing(tracing_no="TN-A", pdf_url="/a.pdf")
    filing_b = _filing(tracing_no="TN-B", pdf_url="/b.pdf")

    calls = {"count": 0}

    def fake_pdftotext(cmd, **kwargs):
        calls["count"] += 1
        txt_path = cmd[3]
        with open(txt_path, "w", encoding="utf-8") as handle:
            handle.write(f"text for call {calls['count']}")

    with patch("codal_pdf_cache.urlopen", return_value=_FakeResponse(b"%PDF-fake")), \
         patch("codal_pdf_cache.subprocess.run", side_effect=fake_pdftotext):
        result_a = codal_pdf_cache.extracted_text_for_filing(filing_a, www_base="https://www.codal.ir/")
        result_b = codal_pdf_cache.extracted_text_for_filing(filing_b, www_base="https://www.codal.ir/")

    assert result_a == "text for call 1"
    assert result_b == "text for call 2"


def test_audit_and_related_party_parsers_share_one_download_for_the_same_filing(tmp_path, monkeypatch):
    # These two parsers used to independently download and pdftotext the
    # same filing PDF -- one real HTTP fetch and subprocess call per parser,
    # per request. They now both go through codal_pdf_cache, so the second
    # parser call for the same filing must be a pure cache hit.
    _use_isolated_cache(tmp_path, monkeypatch)
    filing = _filing()

    with patch("codal_pdf_cache.urlopen", return_value=_FakeResponse(b"%PDF-fake")) as mock_urlopen, \
         patch("codal_pdf_cache.subprocess.run", side_effect=_fake_pdftotext) as mock_run:
        audit_parser.audit_opinion_from_pdf(filing)
        related_party.related_party_flags_from_pdf(filing)

    mock_urlopen.assert_called_once()
    mock_run.assert_called_once()
