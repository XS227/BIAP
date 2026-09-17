import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instrument_classifier import (
    CATEGORY_BANK,
    CATEGORY_BOND_DEBT,
    CATEGORY_COMMODITY_INSTRUMENT,
    CATEGORY_FUND_ETF,
    CATEGORY_HOLDING_COMPANY,
    CATEGORY_INSURANCE_COMPANY,
    CATEGORY_INVESTMENT_COMPANY,
    CATEGORY_LISTED_FINANCIAL_COMPANY,
    CATEGORY_OPERATING_COMPANY,
    CATEGORY_OPTION_DERIVATIVE,
    CATEGORY_RIGHTS_ISSUE,
    CATEGORY_UNKNOWN,
    COMPANY_CATEGORIES,
    base_issuer_symbol,
    classify_instrument,
    issuer_key,
)


def _cat(**kwargs) -> str:
    return classify_instrument(**kwargs).category


def test_ordinary_share_classifies_as_operating_company():
    assert _cat(symbol="فولاد", name="فولاد مبارکه اصفهان", market="TSE", paper_type="300") == CATEGORY_OPERATING_COMPANY
    assert _cat(symbol="آریا", name="پتروشیمی آریا ساسول", market=None, paper_type="303") == CATEGORY_OPERATING_COMPANY


def test_bank_classification_beats_generic_operating_company():
    assert _cat(symbol="وبملت", name="بانک ملت", market="TSE", paper_type="300") == CATEGORY_BANK


def test_insurance_classification():
    assert _cat(symbol="ودی", name="بیمه دی", market="TSE", paper_type="300") == CATEGORY_INSURANCE_COMPANY


def test_investment_company_classification():
    assert _cat(symbol="وغدیر", name="سرمایه گذاری غدیر", market="TSE", paper_type="300") == CATEGORY_INVESTMENT_COMPANY


def test_holding_company_classification():
    assert _cat(symbol="فارس", name="هلدینگ خلیج فارس", market="TSE", paper_type="300") == CATEGORY_HOLDING_COMPANY
    assert (
        _cat(symbol="وتوسم", name="سرمایه گذاری گروه توسعه ملی", market="TSE", paper_type="300")
        == CATEGORY_HOLDING_COMPANY
    )


def test_listed_financial_company_classification():
    assert _cat(symbol="ولیز", name="لیزینگ ایران", market="TSE", paper_type="300") == CATEGORY_LISTED_FINANCIAL_COMPANY
    assert _cat(symbol="کارگزار", name="کارگزاری آگاه", market="TSE", paper_type="300") == CATEGORY_LISTED_FINANCIAL_COMPANY


def test_fund_etf_classification_not_operating_company():
    result = _cat(symbol="آکورد", name="صندوق سرمایه گذاری آکورد", market="TSE", paper_type="300")
    assert result == CATEGORY_FUND_ETF
    assert result != CATEGORY_OPERATING_COMPANY


def test_bond_debt_classification():
    assert _cat(symbol="اخزا1", name="اوراق خزانه اسلامی", market=None, paper_type=None) == CATEGORY_BOND_DEBT
    assert _cat(symbol="صکوک1", name="صکوک اجاره دولت", market=None, paper_type=None) == CATEGORY_BOND_DEBT


def test_bond_debt_classification_participation_and_salaf_contracts():
    """Real production names: مشارکت (participation bonds) and سلف (Salaf/forward-sale contracts)."""
    assert _cat(symbol="مشهد072", name="مشارکت ش مشهد072-3ماهه23%", market=None, paper_type=None) == CATEGORY_BOND_DEBT
    assert _cat(symbol="عقیر1", name="سلف پارس بهین پالایش قشم", market=None, paper_type=None) == CATEGORY_BOND_DEBT


def test_option_derivative_classification():
    assert _cat(symbol="ضفولاد", name="اختیار خرید فولاد", market=None, paper_type=None) == CATEGORY_OPTION_DERIVATIVE


def test_option_derivative_classification_abbreviated_tsetmc_form():
    """Real TSETMC option names abbreviate اختیار خرید/فروش to اختیارخ/اختیارف with no space."""
    assert _cat(symbol="ضهرم8031", name="اختيارخ اهرم-62000-1405/08/27", market=None, paper_type=None) == CATEGORY_OPTION_DERIVATIVE
    assert _cat(symbol="طتاص7012", name="اختيارف تاصيكو-21520-05/07/08", market=None, paper_type=None) == CATEGORY_OPTION_DERIVATIVE


def test_futures_classification_real_contract_names():
    assert _cat(symbol="جهرم0508", name="آتي اهرم-1405/08/27", market=None, paper_type=None) == CATEGORY_OPTION_DERIVATIVE
    assert _cat(symbol="جخود0508", name="آتي خودرو-1405/08/06", market=None, paper_type=None) == CATEGORY_OPTION_DERIVATIVE


def test_futures_keyword_does_not_collide_with_atiyeh_word():
    """"آتیه" (posterity/heritage) is a common, unrelated word in real company/fund
    names and must never be misread as the آتی (futures) keyword."""
    assert _cat(symbol="اپرداز", name="آتیه داده پرداز", market=None, paper_type=None) != CATEGORY_OPTION_DERIVATIVE
    result = _cat(symbol="واتي", name="سرمايه گذاري آتيه دماوند", market=None, paper_type=None)
    assert result == CATEGORY_INVESTMENT_COMPANY


def test_fund_classification_takes_priority_over_futures_mention_in_strategy_name():
    """A commodity/futures-strategy fund's own name may mention آتی without the
    instrument itself being a futures contract -- صندوق must win."""
    assert _cat(symbol="رزگلد", name="صندوق س. كالاي آرمان آتي", market=None, paper_type=None) == CATEGORY_FUND_ETF
    assert _cat(symbol="آكورد", name="صندوق س. آرمان آتي كوثر-د", market=None, paper_type=None) == CATEGORY_FUND_ETF


def test_fund_classification_abbreviated_dot_prefix():
    """Real production funds: "ص.<name>"/"ص.س.<name>" abbreviated prefix, not the full صندوق word."""
    assert _cat(symbol="آسود", name="ص.س.درآمد ثابت آرمان اقتصاد-د", market="TSE", paper_type="300") == CATEGORY_FUND_ETF
    assert _cat(symbol="كيميا", name="ص. معدني كيمياي زنجان گستران", market="TSE", paper_type="300") == CATEGORY_FUND_ETF


def test_bond_debt_classification_agricultural_credit_certificate():
    assert _cat(symbol="گام0602162", name="گواهی اعتبارمولد کشاورزی060231", market=None, paper_type=None) == CATEGORY_BOND_DEBT


def test_rights_issue_abbreviated_dot_prefix_and_bare_symbol_suffix():
    """Real production rights issues: "ح.<name>" prefix (not the full حق تقدم phrase)
    and a bare ح-suffixed symbol, which must not fall through to a keyword match
    on the underlying company's own sector (bank/insurance/investment/holding)."""
    assert _cat(symbol="حياتح", name="ح.بيمه زندگي مفيد", market=None, paper_type=None) == CATEGORY_RIGHTS_ISSUE
    assert _cat(symbol="اعتلاح", name="ح سرمایه گذاری اعتلاء البرز", market=None, paper_type=None) == CATEGORY_RIGHTS_ISSUE
    assert _cat(symbol="وآتوسح", name="ح .گروه سرمايه گذاري توسكا", market=None, paper_type=None) == CATEGORY_RIGHTS_ISSUE
    assert _cat(symbol="کچادح", name="ح . معدنیوصنعتیچادرملو", market=None, paper_type=None) == CATEGORY_RIGHTS_ISSUE


def test_verified_issuer_signal_only_widens_operating_company_fallback():
    # Without a verified-issuer signal and no other evidence, stays unknown.
    assert _cat(symbol="زگلدشت", name="كشت و دام گلدشت نمونه اصفهان", market=None, paper_type=None) == CATEGORY_UNKNOWN
    # An out-of-band verified signal (e.g. CODAL directory match) resolves it.
    result = classify_instrument(symbol="زگلدشت", name="كشت و دام گلدشت نمونه اصفهان", market=None, paper_type=None, verified_issuer=True)
    assert result.category == CATEGORY_OPERATING_COMPANY

    # But it never overrides an actual non-company keyword match.
    fund_result = classify_instrument(symbol="آکورد", name="صندوق سرمایه گذاری آکورد", market=None, paper_type=None, verified_issuer=True)
    assert fund_result.category == CATEGORY_FUND_ETF


def test_rights_issue_classification_by_name_and_yval():
    assert _cat(symbol="فولادح", name="حق تقدم فولاد مبارکه", market=None, paper_type=None) == CATEGORY_RIGHTS_ISSUE
    # Verified production yVal for rights issues even when the name lacks the phrase.
    assert _cat(symbol="فولادح", name="فولادح", market=None, paper_type="400") == CATEGORY_RIGHTS_ISSUE


def test_commodity_instrument_classification():
    assert _cat(symbol="سکه1", name="گواهی سپرده سکه طلا", market=None, paper_type=None) == CATEGORY_COMMODITY_INSTRUMENT


def test_unmatched_non_equity_row_is_unknown_not_fabricated():
    result = _cat(symbol="XYZ123", name="", market=None, paper_type="999")
    assert result == CATEGORY_UNKNOWN


def test_company_categories_set_is_closed_and_excludes_non_company_types():
    assert CATEGORY_OPERATING_COMPANY in COMPANY_CATEGORIES
    assert CATEGORY_BANK in COMPANY_CATEGORIES
    assert CATEGORY_FUND_ETF not in COMPANY_CATEGORIES
    assert CATEGORY_BOND_DEBT not in COMPANY_CATEGORIES
    assert CATEGORY_RIGHTS_ISSUE not in COMPANY_CATEGORIES
    assert CATEGORY_UNKNOWN not in COMPANY_CATEGORIES


def test_base_issuer_symbol_strips_rights_suffix():
    assert base_issuer_symbol("فولادح", "حق تقدم فولاد", CATEGORY_RIGHTS_ISSUE) == "فولاد"
    assert base_issuer_symbol("فولاد", "فولاد مبارکه", CATEGORY_OPERATING_COMPANY) == "فولاد"


def test_issuer_key_links_rights_issue_to_same_company_as_base_share():
    base_key = issuer_key("فولاد", "فولاد مبارکه اصفهان", CATEGORY_OPERATING_COMPANY)
    rights_key = issuer_key("فولادح", "حق تقدم فولاد مبارکه اصفهان", CATEGORY_RIGHTS_ISSUE)
    assert base_key == rights_key
    assert base_key is not None


def test_issuer_key_is_none_for_non_company_categories():
    assert issuer_key("آکورد", "صندوق سرمایه گذاری آکورد", CATEGORY_FUND_ETF) is None
    assert issuer_key("اخزا1", "اوراق خزانه", CATEGORY_BOND_DEBT) is None
    assert issuer_key("XYZ", "", CATEGORY_UNKNOWN) is None
