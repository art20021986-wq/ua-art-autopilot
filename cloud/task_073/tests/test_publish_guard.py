import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import publish_guard as pg


class TestPublishGuard(unittest.TestCase):
    def test_placeholder_created_when_no_diagnostics(self):
        with tempfile.TemporaryDirectory() as prod:
            index = {}
            result = pg.publish_card("UA-0011", "<html>primary</html>", None, prod, index, lambda c, r: True)
            self.assertTrue(result.success)
            diag_path = os.path.join(prod, "UA-0011-diag.html")
            self.assertTrue(os.path.exists(diag_path))
            with open(diag_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn(pg.PLACEHOLDER_DIAG_TEXT, content)

    def test_missing_primary_raises_seo068(self):
        with tempfile.TemporaryDirectory() as prod:
            index = {}
            with self.assertRaises(pg.SEO068DiagnosticMissing):
                pg.publish_card("UA-0011", "", None, prod, index, lambda c, r: True)

    def test_failed_verify_never_reports_success(self):
        with tempfile.TemporaryDirectory() as prod:
            index = {}
            result = pg.publish_card("UA-0011", "<html>primary</html>", None, prod, index, lambda c, r: False)
            self.assertFalse(result.success)
            self.assertIn("verify_failed", result.message)

    def test_idempotent_second_publish_no_duplicate(self):
        with tempfile.TemporaryDirectory() as prod:
            index = {}
            r1 = pg.publish_card("UA-0011", "<html>primary</html>", None, prod, index, lambda c, r: True)
            r2 = pg.publish_card("UA-0011", "<html>primary</html>", None, prod, index, lambda c, r: True)
            self.assertTrue(r1.success and r2.success)
            self.assertEqual(r1.revision, r2.revision)
            self.assertEqual(list(index.keys()).count("UA-0011"), 1)

    def test_real_diagnostics_not_replaced_by_placeholder(self):
        with tempfile.TemporaryDirectory() as prod:
            index = {}
            real_diag = "<html>real diagnostics content</html>"
            result = pg.publish_card("UA-9913", "<html>primary</html>", real_diag, prod, index, lambda c, r: True)
            self.assertTrue(result.success)
            with open(os.path.join(prod, "UA-9913-diag.html"), encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("real diagnostics content", content)
            self.assertNotIn(pg.PLACEHOLDER_DIAG_TEXT, content)


if __name__ == "__main__":
    unittest.main()
