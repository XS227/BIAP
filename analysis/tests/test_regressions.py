from agents import fundamental_agent
from audit_parser import (
    _extract_audit_opinion_section,
    classify_audit_opinion_from_text,
)
from codal_data import CodalFiling, _row_values
from financial_scope import (
    CONSOLIDATED,
    STANDALONE,
    report_scope_from_title,
    select_scope_filings,
)
from related_party import _related_party_flags_from_text
import symbol_universe as su
from symbol_universe import MarketSymbol


def test_exact_net_profit_row_matching():
    rows = [
        ["سود (زیان) خالص عملیات متوقف شده", "0", "0"],
        ["سود(زیان) خالص", "100", "80"],
    ]

    result = _row_values(
        rows,
        ("سود (زیان) خالص", "سود خالص", "زیان خالص"),
    )

    assert result == (100.0, 80.0)


def test_negative_margin_is_penalized_even_if_improving():
    company = {
        "codal": {
            "revenue_yoy_pct": 56.8,
            "net_margin_pct": -0.9,
            "net_margin_prev_pct": -1.7,
            "audit_opinion": None,
            "related_party_flags": None,
        },
        "market": {},
    }

    result = fundamental_agent(company)

    assert result.vote == 0.1
    assert "net margin negative" in result.reasoning
    assert "loss margin improving" in result.reasoning


def test_bounded_audit_parser_ignores_exception_outside_opinion_section():
    text = """
    اظهارنظر
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت را
    از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان می دهد.
    مبنای اظهارنظر
    شواهد حسابرسی کافی و مناسب کسب شده است.
    سایر اطلاعات
    موجودی مواد و کالا به استثنای موجودی کالای در راه بررسی شده است.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "موجودی مواد و کالا" not in section
    assert classify_audit_opinion_from_text(text) == "unqualified"


def test_bounded_audit_parser_detects_qualified_opinion_inside_section():
    text = """
    اظهارنظر
    به نظر این سازمان، به استثنای آثار موضوع شرح داده شده در بند مبنای
    اظهارنظر مشروط، صورتهای مالی از تمام جنبه های با اهمیت به نحو
    منصفانه نشان می دهد.
    مبنای اظهارنظر
    موضوع محدودیت رسیدگی در این بخش تشریح شده است.
    """

    assert classify_audit_opinion_from_text(text) == "qualified"


def test_bounded_audit_parser_requires_reliable_opinion_anchor():
    text = """
    یادداشت موجودی کالا شامل عبارت به استثنای کالای در راه است.
    اطلاعات دیگری نیز در صورتهای مالی ارائه شده است.
    """

    assert classify_audit_opinion_from_text(text) is None


def test_bounded_audit_parser_detects_disclaimer_of_opinion():
    text = """
    اظهارنظر
    با توجه به عدم دسترسی به شواهد حسابرسی کافی و مناسب در خصوص موجودی
    کالا، این سازمان قادر به اظهارنظر نسبت به صورتهای مالی نیست. بر این
    اساس، عدم اظهارنظر نسبت به صورتهای مالی ارائه می شود.
    مبنای عدم اظهارنظر
    محدودیت رسیدگی در این بخش تشریح شده است.
    """

    # "مبنای عدم اظهارنظر" must not itself be picked as the opinion heading
    # (it contains "اظهارنظر" as a substring); the section should start at
    # the real "اظهارنظر" heading above it.
    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert section.startswith("اظهارنظر")
    assert classify_audit_opinion_from_text(text) == "disclaimer"


def test_bounded_audit_parser_detects_adverse_opinion():
    text = """
    اظهارنظر
    به نظر این سازمان، به علت اهمیت موضوعات مندرج در بند مبنای اظهارنظر
    مردود، صورتهای مالی وضعیت مالی شرکت را به نحو مطلوب نشان نمی دهد.
    مبنای اظهارنظر مردود
    آثار موضوعات مورد اشاره در این بخش تشریح شده است.
    """

    assert classify_audit_opinion_from_text(text) == "adverse"


def test_bounded_audit_parser_prefers_real_section_over_table_of_contents():
    # Without a canonical fairness clause to anchor on (real for a disclaimer,
    # which never confirms the statements are fairly presented), a naive
    # "first heading wins" rule would grab the table-of-contents entry instead
    # of the actual opinion section further down the document.
    text = """
    فهرست مطالب
    اظهارنظر
    سایر مطالب
    این بخش صرفا فهرست گزارش است و شامل هیچ اظهارنظری نیست.

    گزارش حسابرس مستقل
    اظهارنظر
    با توجه به عدم دسترسی به شواهد حسابرسی کافی و مناسب، این سازمان
    قادر به اظهارنظر نسبت به صورتهای مالی نیست. عدم اظهارنظر نسبت به
    صورتهای مالی ارائه می شود.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "فهرست" not in section
    assert classify_audit_opinion_from_text(text) == "disclaimer"


def test_bounded_audit_parser_does_not_mistake_basis_heading_for_opinion_heading():
    # "مبنای اظهارنظر" ("Basis for Opinion") contains "اظهارنظر" as a
    # substring and must never itself be picked as the opinion heading.
    text = """
    مبنای اظهارنظر
    شواهد حسابرسی کافی و مناسب کسب شده است.
    اظهارنظر
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت را
    از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان می دهد.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "شواهد حسابرسی کافی" not in section
    assert classify_audit_opinion_from_text(text) == "unqualified"


def test_related_party_parser_returns_none_without_context():
    text = "صورتهای مالی طبق استانداردهای حسابداری تهیه شده است."

    assert _related_party_flags_from_text(text) is None


def test_related_party_routine_disclosure_is_not_a_flag():
    text = """
    معاملات با اشخاص وابسته در یادداشت های توضیحی صورتهای مالی افشا شده است.
    مانده حسابهای اشخاص وابسته نیز در صورتهای مالی ارائه شده است.
    """

    assert _related_party_flags_from_text(text) == 0


def test_related_party_explicit_noncompliance_is_flagged():
    text = """
    در بررسی معاملات با اشخاص وابسته مشخص شد ماده 129 قانون تجارت رعایت نشده
    و بخشی از معاملات اشخاص وابسته افشا نشده است.
    """

    assert _related_party_flags_from_text(text) == 2


def _filing(title: str) -> CodalFiling:
    return CodalFiling(
        tracing_no=None,
        title=title,
        sent_at=None,
        publish_at=None,
        letter_code=None,
        url=None,
        pdf_url=None,
        excel_url=None,
        attachment_url=None,
    )


def test_report_scope_classifies_consolidated_and_standalone():
    assert report_scope_from_title("صورت های مالی تلفیقی سال مالی منتهی به 1404/12/29") == CONSOLIDATED
    assert report_scope_from_title("صورت های مالی سال مالی منتهی به 1404/12/29") == STANDALONE
    assert report_scope_from_title("تصمیمات مجمع عمومی عادی سالیانه") is None


def test_report_scope_prefers_consolidated_when_both_exist():
    standalone = _filing("صورت های مالی سال مالی منتهی به 1404/12/29")
    consolidated = _filing("صورت های مالی تلفیقی سال مالی منتهی به 1404/12/29")

    scope, filings = select_scope_filings([standalone, consolidated])

    assert scope == CONSOLIDATED
    assert filings == [consolidated]


def test_report_scope_falls_back_to_standalone():
    standalone = _filing("صورت های مالی سال مالی منتهی به 1404/12/29")

    scope, filings = select_scope_filings([standalone])

    assert scope == STANDALONE
    assert filings == [standalone]


def test_symbol_snapshot_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "symbols.json"
    monkeypatch.setenv("BIAP_SYMBOL_SNAPSHOT", str(path))
    items = [
        MarketSymbol(
            code="123",
            symbol="فولاد",
            name="فولاد مبارکه اصفهان",
            market="TSE",
            flow=1,
            industry_code="27",
            paper_type="300",
            source="tsetmc",
        )
    ]

    su._save_snapshot(items)
    loaded = su._load_snapshot()

    assert loaded == items


def test_symbol_universe_uses_verified_snapshot_when_upstreams_fail(tmp_path, monkeypatch):
    path = tmp_path / "symbols.json"
    monkeypatch.setenv("BIAP_SYMBOL_SNAPSHOT", str(path))
    cached = [
        MarketSymbol(
            code="123",
            symbol="فولاد",
            name="فولاد مبارکه اصفهان",
            market="TSE",
            flow=1,
            industry_code="27",
            paper_type="300",
            source="tsetmc",
        )
    ]
    su._save_snapshot(cached)
    su._cache = None
    monkeypatch.setattr(su, "_fetch_json_universe", lambda **kwargs: [])
    monkeypatch.setattr(su, "_fetch_legacy_universe", lambda **kwargs: [])
    monkeypatch.setattr(su, "_fetch_codal_universe", lambda: [])

    result = su.fetch_symbol_universe(use_cache=False)

    assert result == cached
