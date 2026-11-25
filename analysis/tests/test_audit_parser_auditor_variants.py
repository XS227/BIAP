"""Audit opinion wording: private audit firms say «این موسسه», not «این سازمان»."""
import audit_parser as ap

UNQ = "به نظر این موسسه صورت‌های مالی یادشده از تمام جنبه‌های بااهمیت وضعیت مالی را به نحو منصفانه نشان می‌دهد"


def test_private_firm_clean_opinion():
    assert ap._classify_audit_opinion_section("اظهارنظر\n" + UNQ.replace("می‌ده", "می ده")) == "unqualified"


def test_state_org_clean_opinion_still_works():
    t = "به نظر این سازمان صورتهای مالی به نحو منصفانه نشان میدهد"
    assert ap._classify_audit_opinion_section(t) == "unqualified"


def test_exception_before_fair_clause_is_qualified():
    t = "به نظر این موسسه به استثنا آثار موارد بند مبنا صورتهای مالی به نحو منصفانه نشان می دهد"
    assert ap._classify_audit_opinion_section(t) == "qualified"


def test_unknown_text_not_classified():
    assert ap._classify_audit_opinion_section("متن نامرتبط") is None
