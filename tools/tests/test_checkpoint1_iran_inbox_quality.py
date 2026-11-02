import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.checkpoint1_iran_inbox_quality import issuer_evidence, normalized_name, audit_symbol


class TestIssuerEvidence(unittest.TestCase):
    def test_arabic_persian_variants(self):
        self.assertEqual(normalized_name("شركت ايران خودرو"), normalized_name("ایران خودرو"))

    def test_subsidiary_is_not_assumed_parent(self):
        self.assertEqual(issuer_evidence("صورت‌های مالی (شرکت لاستیک بارز کردستان)", "گروه صنعتی بارز"),
                         "EXPLICIT_ISSUER_REVIEW")

    def test_exact_named_issuer(self):
        self.assertEqual(issuer_evidence("صورت‌های مالی (شرکت ایران خودرو)", "ایران خودرو"),
                         "EXPLICIT_ISSUER_MATCH")

    def test_no_named_issuer_is_unverified(self):
        self.assertEqual(issuer_evidence("صورت‌های مالی تلفیقی حسابرسی شده", "ایران خودرو"),
                         "ISSUER_NOT_EXPLICIT")

    def test_no_report_html_is_not_pass(self):
        class InboxStub:
            def record(self, symbol):
                return {"status": "ok", "company": {"n": "ایران خودرو"},
                        "financial_filings": [{"tracing_no": "123", "title": "صورت‌های مالی (شرکت دیگر)"}]}
            def report_html(self, tracing_no):
                raise RuntimeError("not found")
        result = audit_symbol(InboxStub(), "خودرو")
        self.assertEqual(result["explicit_issuer_review"], 1)
        self.assertEqual(result["html_missing"], 1)
        self.assertTrue(result["audit_status"].startswith("BLOCKED"))


if __name__ == "__main__":
    unittest.main()
