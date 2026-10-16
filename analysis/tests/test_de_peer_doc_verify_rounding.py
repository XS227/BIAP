import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "validation" / "tools"))
sys.argv = ["x", "/tmp", "/tmp/c.json", "/tmp/o.json"]
import de_peer_doc_verify as v  # noqa: E402


def test_teur_figure_rounding_to_stored_two_decimal_millions():
    assert v.matches_rounded_teur("Jahresergebnis 5.695 TEUR (Vj. 3.112 TEUR)", 5_690_000.0)   # LIMES 5,694,977 -> 5.69m
    assert v.matches_rounded_teur("Group earnings T€ 9,928", 9_930_000.0)                       # GESCO
    assert v.matches_rounded_teur("Umsatzerlöse T€ 69.237", 69_240_000.0)                       # FHW
    assert v.matches_rounded_teur("Owners of the parent 8,571", 8_570_000.0)                    # OVB


def test_whole_eur_figure_rounds_to_stored():
    assert v.matches_rounded_teur("davon Umsatzerlöse 49.996.628", 50_000_000.0)


def test_no_false_match_when_document_does_not_print_it():
    assert not v.matches_rounded_teur("Konzernergebnis 24.698 Gesamtergebnis 26.397", 26_400_000.0 + 100_000)
    assert not v.matches_rounded_teur("Revenue 1,566 million total", 1_579_100_000.0)           # LEG: stored value not printed
    assert not v.matches_rounded_teur("Net income 9,928", 9_930_001.0)                          # not 10k-precise -> not eligible
    assert not v.matches_rounded_teur("9,928", None)


def test_dbag_comprehensive_income_is_not_net_income():
    # stored 26.4m is Konzern-Gesamtergebnis (26,397); a net-income match must come from Konzernergebnis 24,698 only
    assert not v.matches_rounded_teur("Konzernergebnis 24.698 -35.227", 26_400_000.0)


def test_net_income_rounded_match_needs_attribution_label_and_skips_comprehensive_income():
    lab = v.NI_ATTRIBUTION_LABEL
    assert v.matches_rounded_teur("Profit share of shareholders in SNP 31,816 20,244", 31_820_000.0, lab)
    assert not v.matches_rounded_teur("Konzern-Gesamtergebnis 26.397 -35.056", 26_400_000.0, lab)   # DBAG: comprehensive income
    assert not v.matches_rounded_teur("Total assets 9,928", 9_930_000.0, lab)                        # no net-income context


def test_esef_zip_package_text_is_extracted(tmp_path):
    import zipfile
    z = tmp_path / "pkg.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("reports/r.xhtml", "<html><body><script>x()</script><p>Revenue 296,770</p></body></html>")
        f.writestr("META-INF/x.xml", "<a>ignored</a>")
    txt = v.to_text(z, "application/zip")
    assert "Revenue 296,770" in txt and "x()" not in txt and "ignored" not in txt
