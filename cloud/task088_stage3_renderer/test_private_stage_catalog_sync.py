"""Exercise the pinned real stage process on isolated in-memory HTML only."""

import ast
import copy
import json
import os
from pathlib import Path
import unittest

from patch_stage_catalog_sync import patch_stage_catalog_sync
from uaart_market_prices import END, START, render_market_prices
from initial_html_prices import migrate_catalog


def article(row, *, managed=True):
    price = render_market_prices(row, compact=True, require_car_id=True) if managed else '<b>12 000 $</b>'
    return ('<article class="catalog-card" data-stage="georgia" data-ua-stage="3">'
        '<div class="catalog-top"><span>UA-0001</span>' + price + '</div>'
        '<h2>Protected title</h2><img src="keep-photo.jpg"><a href="UA-0001.html">Card</a>'
        '<div class="status-pill" data-ru="В Грузии · описание" '
        'data-uk="У Грузії · опис">В Грузии · описание</div>'
        '<div class="ua-cat-vin-v1" data-ua-card="UA-0001" data-ua-stage-tile="3" '
        'data-category="gruzia">VIN PRESERVED1234</div>'
        '<details><summary>Additional specification</summary>Protected equipment</details>'
        '</article>')


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class StageCatalogVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = Path(os.environ["UA088_LIVE_SOURCE_DIR"])
        cls.original = (cls.capture / "ua_stage_catalog_sync.py").read_bytes()
        cls.candidate, cls.receipt = patch_stage_catalog_sync(cls.original)
        cls.before, cls.after = {}, {}
        for raw, namespace in ((cls.original, cls.before), (cls.candidate, cls.after)):
            # Exact hash-pinned standard-library-only module; __main__ remains off.
            namespace["__name__"] = "isolated_stage_catalog_test"
            exec(compile(raw, "isolated_stage_catalog_test.py", "exec"), namespace)

    def row(self, status="ge_waiting", price_georgia=9000):
        return dict(auto_number="UA-0001", status=status, price_uah=12000,
                    price_georgia=price_georgia, published=1, title="Protected title")

    def test_kyiv_transition_changes_only_existing_stage_fields_and_managed_price(self):
        previous = self.row()
        current = self.row("ua_arrived")
        rows = {current["auto_number"]: current}
        preserved = copy.deepcopy(rows)
        source = '<head>Protected SEO</head>' + article(previous) + '<footer>Protected buttons</footer>'
        expected_stage, _ = self.before["patch_catalog_stages"](source, rows)
        actual, changed = self.after["patch_catalog_stages"](source, rows)
        self.assertEqual(changed, ["UA-0001"])
        old_fragment = render_market_prices(previous, compact=True, require_car_id=True)
        new_fragment = render_market_prices(current, compact=True, require_car_id=True)
        self.assertEqual(actual.replace(new_fragment, old_fragment, 1), expected_stage)
        self.assertNotIn('data-ua-market="georgia"', actual)
        self.assertEqual(rows, preserved)
        self.assertEqual(rows["UA-0001"]["price_georgia"], 9000)

    def test_leaving_kyiv_restores_current_stored_ge_price_and_is_idempotent(self):
        source = article(self.row("ua_arrived"))
        current = self.row("ge_waiting", 9700)
        actual, changed = self.after["patch_catalog_stages"](source, {"UA-0001": current})
        self.assertEqual(changed, ["UA-0001"])
        self.assertIn('data-ua-market="georgia"', actual)
        self.assertIn('data-ua-field="price_georgia" data-ua-value="9700"', actual)
        again, changed = self.after["patch_catalog_stages"](actual, {"UA-0001": current})
        self.assertEqual(again, actual)
        self.assertEqual(changed, [])

    def test_leaving_kyiv_with_nullable_ge_restores_localized_placeholder(self):
        row = self.row("sea_ready", None)
        actual, _ = self.after["patch_catalog_stages"](article(self.row("ua_arrived", None)), {"UA-0001": row})
        self.assertIn('data-ua-field="price_georgia" data-ua-value=""', actual)
        for text in ("Цена уточняется", "Ціна уточнюється", "ფასი ზუსტდება"):
            self.assertIn(text, actual)
        self.assertNotIn('>0 $<', actual)

    def test_legacy_unmarked_articles_retain_exact_old_price_behavior(self):
        source = article(self.row(), managed=False)
        rows = {"UA-0001": self.row("ua_arrived")}
        self.assertEqual(self.after["patch_catalog_stages"](source, rows),
                         self.before["patch_catalog_stages"](source, rows))
        self.assertNotIn(START, self.after["patch_catalog_stages"](source, rows)[0])

    def test_partial_or_misplaced_markers_fail_before_any_candidate_is_returned(self):
        valid = article(self.row())
        rows = {"UA-0001": self.row("ua_arrived")}
        for source in (valid.replace(START, ""), valid.replace(END, ""),
                       valid.replace(START, "", 1).replace('<h2>', START + '<h2>', 1)):
            with self.subTest(source=source[:30]), self.assertRaisesRegex(ValueError, "MARKER_LOCATION"):
                self.after["patch_catalog_stages"](source, rows)

    def test_source_drift_rejected_and_transaction_function_is_byte_identical(self):
        for raw in (self.original + b"\n", self.candidate):
            with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
                patch_stage_catalog_sync(raw)
        before_tree, after_tree = ast.parse(self.original), ast.parse(self.candidate)
        before = next(node for node in before_tree.body if isinstance(node, ast.FunctionDef) and node.name == "reconcile")
        after = next(node for node in after_tree.body if isinstance(node, ast.FunctionDef) and node.name == "reconcile")
        self.assertEqual(ast.get_source_segment(self.original.decode(), before),
                         ast.get_source_segment(self.candidate.decode(), after))
        self.assertTrue(self.receipt["legacy_unmarked_prices_unchanged"])

    def test_all_captured_catalogs_preserve_every_byte_when_stage_and_prices_match(self):
        rows = json.loads((self.capture / "published_price_rows.json").read_text())
        by_code = {row["auto_number"]: row for row in rows}
        for folder in ("video", "site"):
            with self.subTest(folder=folder):
                source = (self.capture / folder / "katalog.html").read_text()
                prepared, _ = migrate_catalog(source, rows)
                actual, changed = self.after["patch_catalog_stages"](prepared, by_code)
                self.assertEqual(actual, prepared)
                self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
