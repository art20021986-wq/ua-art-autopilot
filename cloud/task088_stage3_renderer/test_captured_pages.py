"""Reproducible checks against private captured HTML and CRM price-only rows."""

import hashlib
import html
import json
import os
import pathlib
import re
import unittest

from initial_html_prices import migrate_card, migrate_catalog
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


if __name__ == "__main__":
    unittest.main()
