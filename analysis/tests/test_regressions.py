from agents import fundamental_agent
from codal_data import _row_values
from related_party import _related_party_flags_from_text


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


def test_audit_opinion_unqualified_phrase():
    from codal_data import _classify_audit_opinion

    text = """
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت
    را از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان می دهد.
    """

    assert _classify_audit_opinion(text) == "unqualified"


def test_audit_opinion_ignores_unrelated_exception_text():
    from codal_data import _classify_audit_opinion

    text = """
    مبنای اظهارنظر، کافی و مناسب است.
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت را
    از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان میدهد.
    تاکید بر مطالب خاص.
    موجودی مواد و کالا به استثنای موجودی کالای در راه بررسی شده است.
    """

    assert _classify_audit_opinion(text) == "unqualified"


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
