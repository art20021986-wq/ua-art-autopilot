import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bundle_publisher_v3 as bp  # noqa: E402


class TestBundlePublisher(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="task073_test_")
        self.targets = bp.CardTargets(
            auto_number="UA-0011",
            primary_path=os.path.join(self.tmp_dir, "UA-0011.html"),
            diag_path=os.path.join(self.tmp_dir, "UA-0011-diag.html"),
            catalog_path=os.path.join(self.tmp_dir, "katalog.html"),
        )
        self.all_numbers = ["UA-{:04d}".format(i) for i in range(1, 11)] + ["UA-0011"]

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dry_run_does_not_write_files(self):
        result = bp.publish_card(self.targets, self.all_numbers, None, proba=True)
        self.assertTrue(result.ok)
        self.assertFalse(os.path.exists(self.targets.primary_path))

    def test_real_publish_creates_placeholder_and_catalog_once(self):
        result = bp.publish_card(self.targets, self.all_numbers, None, proba=False)
        self.assertTrue(result.ok)
        with open(self.targets.diag_path, "r", encoding="utf-8") as fh:
            diag_text = fh.read()
        self.assertIn(bp.DIAG_PLACEHOLDER_TEXT, diag_text)
        with open(self.targets.catalog_path, "r", encoding="utf-8") as fh:
            catalog_text = fh.read()
        self.assertEqual(catalog_text.count('href="UA-0011.html"'), 1)

    def test_idempotent_repeat_no_duplicate(self):
        bp.publish_card(self.targets, self.all_numbers, None, proba=False)
        result2 = bp.publish_card(self.targets, self.all_numbers, None, proba=False)
        self.assertTrue(result2.ok)
        with open(self.targets.catalog_path, "r", encoding="utf-8") as fh:
            catalog_text = fh.read()
        self.assertEqual(catalog_text.count('href="UA-0011.html"'), 1)

    def test_real_diagnostics_material_not_overwritten_by_placeholder(self):
        self.targets.has_diag_material = True
        real_diag = "<html><body>UA-0011 real diagnostics content</body></html>"
        result = bp.publish_card(self.targets, self.all_numbers, real_diag, proba=False)
        self.assertTrue(result.ok)
        with open(self.targets.diag_path, "r", encoding="utf-8") as fh:
            diag_text = fh.read()
        self.assertIn("real diagnostics content", diag_text)
        self.assertNotIn(bp.DIAG_PLACEHOLDER_TEXT, diag_text)

    def test_validation_failure_rolls_back_and_creates_no_files(self):
        original = bp.render_primary_html
        try:
            bp.render_primary_html = lambda auto_number: "<html>no identity</html>"
            result = bp.publish_card(self.targets, self.all_numbers, None, proba=False)
            self.assertFalse(result.ok)
            self.assertFalse(os.path.exists(self.targets.primary_path))
        finally:
            bp.render_primary_html = original

    def test_install_failure_restores_preexisting_target(self):
        with open(self.targets.primary_path, "w", encoding="utf-8") as fh:
            fh.write("PRE_EXISTING_CONTENT")
        original_write = bp._atomic_write

        def failing_write(path, content):
            if path == self.targets.diag_path:
                raise RuntimeError("simulated failure writing diag target")
            original_write(path, content)

        bp._atomic_write = failing_write
        try:
            result = bp.publish_card(self.targets, self.all_numbers, None, proba=False)
            self.assertFalse(result.ok)
            with open(self.targets.primary_path, "r", encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "PRE_EXISTING_CONTENT")
        finally:
            bp._atomic_write = original_write


if __name__ == "__main__":
    unittest.main()
