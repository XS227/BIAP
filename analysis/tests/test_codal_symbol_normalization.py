from company_builder import _canonical_symbol


def test_canonical_symbol_normalizes_arabic_kaf_and_yeh():
    assert _canonical_symbol("كچاد") == "کچاد"
    assert _canonical_symbol("يک") == "یک"


def test_canonical_symbol_removes_directional_marks_and_extra_spaces():
    assert _canonical_symbol("  فولاد\u200f  ") == "فولاد"
