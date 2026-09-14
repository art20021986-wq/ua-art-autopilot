"""Reproducible checks against private captured HTML and CRM price-only rows."""

import hashlib
import html
import json
import os
import pathlib
import re
import unittest

from initial_html_prices import migrate_card, migrate_catalog, migrate_home
from patch_catalog_design_guard import patch_catalog_design_guard
from test_private_catalog_guard import guard_namespace
from uaart_market_prices import START, END, render_market_prices


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class CapturedPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"])
        cls.rows = json.loads((cls.private / "published_price_rows.json").read_text())

    def test_captured_ua0010_changes_only_price_and_known_caption(self):
        raw = (self.private / "video/UA-0010.html").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "f460dc2bcefb2719bbd6a445e23fe00d7d8b2733781cac79aeb36253b070c464")
        source = raw.decode()
        row = next(row for row in self.rows if row["auto_number"] == "UA-0010")
        after, evidence = migrate_card(source, row)
        self.assertEqual(after.count(START), 1)
        self.assertEqual(after.count(END), 1)
        self.assertTrue(evidence["outside_price_unchanged"])
        self.assertIn('data-ua-value="8750"', after)
        self.assertEqual(re.findall(r'<(?:img|a|script)\b[^>]*>', source), re.findall(r'<(?:img|a|script)\b[^>]*>', after))

    def test_actual_golden_and_crm_prices_keep_full_catalog_shell(self):
        golden_raw = (self.private / "catalog_design_golden.html").read_bytes()
        self.assertEqual(hashlib.sha256(golden_raw).hexdigest(), "228aaf503ef9728683020e15cb83c66550b77d45c8d7c341cc87f5f5768eb2c7")
        source = (self.private / "catalog_design_guard.py").read_bytes()
        old = guard_namespace(source)
        new = guard_namespace(patch_catalog_design_guard(source)[0])
        # Fixture photos isolate the price change; this is not photo acceptance.
        photos = {row["auto_number"]: "fixture.jpg" for row in self.rows}
        golden = golden_raw.decode()
        before = old["build_catalog"](golden, self.rows, photos)
        after = new["build_catalog"](golden, self.rows, photos)
        audit = new["audit_catalog"](after, self.rows, golden)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["counts"], {"all": 18, "kiev": 5, "georgia": 5, "sea": 4, "korea": 4})
        restored = after
        for row in self.rows:
            price = html.escape(old["_money"](row), quote=True)
            old_html = '<b data-ru="%s" data-uk="%s">%s</b>' % (price, price, price)
            restored = restored.replace(render_market_prices(row, compact=True, require_car_id=True), old_html, 1)
        self.assertEqual(restored, before)
        self.assertEqual(after.count(START), 18)
        self.assertEqual(after.count(END), 18)

    def test_actual_catalog_initial_migration_preserves_original_guard(self):
        raw = (self.private / "video/katalog.html").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "bb4385cc16f9e6b2f95d20bea5eb0db4c3462eb870fc9acf85815afd078ff0df")
        before = raw.decode()
        after, evidence = migrate_catalog(before, self.rows)
        unchanged_guard = guard_namespace((self.private / "catalog_design_guard.py").read_bytes())
        audit = unchanged_guard["audit_catalog"](after, self.rows, (self.private / "catalog_design_golden.html").read_text())
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["counts"], {"all": 18, "kiev": 5, "georgia": 5, "sea": 4, "korea": 4})
        self.assertEqual(evidence["price_regions_changed"], 18)
        self.assertTrue(evidence["outside_price_unchanged"])
        self.assertEqual(re.findall(r'<(?:img|a|script)\b[^>]*>', before), re.findall(r'<(?:img|a|script)\b[^>]*>', after))
        self.assertEqual(after.count(START), 18)
        self.assertEqual(after.count(END), 18)


_capture_root = pathlib.Path(os.environ.get("UA088_LIVE_SOURCE_DIR", "/snapshot-not-supplied"))


@unittest.skipUnless((_capture_root / "capture_manifest.json").is_file(), "Complete current capture not supplied")
class CompleteCurrentCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = _capture_root
        cls.manifest = json.loads((cls.private / "capture_manifest.json").read_text())
        cls.rows = json.loads((cls.private / "published_price_rows.json").read_text())

    def captured(self, relative):
        raw = (self.private / relative).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.manifest["sha256"][relative])
        return raw.decode("utf-8")

    def test_every_current_published_card_in_both_roots_preserves_protected_markup(self):
        self.assertEqual(len(self.rows), self.manifest["published_count"])
        self.assertEqual(len({row["auto_number"] for row in self.rows}), len(self.rows))
        for directory in ("video", "site"):
            for row in self.rows:
                relative = directory + "/" + row["auto_number"] + ".html"
                with self.subTest(path=relative):
                    source = self.captured(relative)
                    candidate, evidence = migrate_card(source, row)
                    self.assertTrue(evidence["outside_price_unchanged"])
                    self.assertEqual(candidate.count(START), 1)
                    self.assertEqual(candidate.count(END), 1)
                    self.assertIn(render_market_prices(row, require_car_id=True), candidate)
                    pattern = r'<(?:img|a|meta|link|script|title|table|details)\b[^>]*>'
                    self.assertEqual(re.findall(pattern, source), re.findall(pattern, candidate))

    def test_both_current_catalogs_have_one_compact_fragment_per_published_car(self):
        for directory in ("video", "site"):
            with self.subTest(directory=directory):
                source = self.captured(directory + "/katalog.html")
                candidate, evidence = migrate_catalog(source, self.rows)
                self.assertTrue(evidence["outside_price_unchanged"])
                self.assertEqual(candidate.count(START), len(self.rows))
                self.assertEqual(candidate.count(END), len(self.rows))
                for row in self.rows:
                    self.assertIn(render_market_prices(row, compact=True, require_car_id=True), candidate)
                pattern = r'<(?:img|a|meta|link|script|title)\b[^>]*>'
                self.assertEqual(re.findall(pattern, source), re.findall(pattern, candidate))

    def test_actual_stage_home_is_unchanged_and_legacy_car_home_is_not_misclassified(self):
        live_home = self.captured("video/index.html")
        candidate, evidence = migrate_home(live_home, self.rows)
        self.assertEqual(candidate, live_home)
        self.assertTrue(evidence["no_car_price_surfaces"])
        # The captured site/index has old car previews and requires route proof
        # before exclusion as a non-served legacy artifact. Never call it a
        # harmless stage-only homepage or silently publish stale prices.
        with self.assertRaisesRegex(ValueError, "CAR_PRICE_SURFACE_REQUIRES_MIGRATION"):
            migrate_home(self.captured("site/index.html"), self.rows)


if __name__ == "__main__":
    unittest.main()
