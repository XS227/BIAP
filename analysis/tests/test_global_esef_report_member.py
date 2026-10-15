import io
import unittest
import zipfile

from global_markets.oam_esef import _report_member


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    buf.seek(0)
    return zipfile.ZipFile(buf)


class ReportMemberTests(unittest.TestCase):
    def test_prefers_tagged_statements_over_larger_untagged_management_report(self):
        tagged = b"<html><ix:nonFraction name='ifrs-full:Revenue'>1</ix:nonFraction></html>"
        z = _zip({
            "p/reports/KA.xhtml": tagged,
            "p/reports/KLB.xhtml": b"<html>" + b"x" * 5000 + b"</html>",
        })
        self.assertEqual(_report_member(z), "p/reports/KA.xhtml")

    def test_largest_tagged_member_wins(self):
        small = b"<ix:nonFraction name='a'>1</ix:nonFraction>"
        big = small * 20
        z = _zip({"reports/a.xhtml": small, "reports/b.xhtml": big})
        self.assertEqual(_report_member(z), "reports/b.xhtml")

    def test_untagged_package_falls_back_to_largest(self):
        z = _zip({"reports/a.xhtml": b"<html>a</html>", "reports/b.xhtml": b"<html>bbbbbb</html>"})
        self.assertEqual(_report_member(z), "reports/b.xhtml")

    def test_no_members(self):
        self.assertIsNone(_report_member(_zip({"x.txt": b"1"})))


if __name__ == "__main__":
    unittest.main()
