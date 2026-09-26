#!/usr/bin/env python3
import ast
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe

FULL = ('<!-- UA-ART-MARKET-PRICES-V1:START --><div class="ua-market-prices-v1">'
        '<div data-ua-market="ukraine" data-ua-field="price_uah" data-ua-value="21200"></div>'
        '<div data-ua-market="georgia" data-ua-field="price_georgia" data-ua-value="17500"></div>'
        '</div><!-- UA-ART-MARKET-PRICES-V1:END -->')


class ProbeHelpers(unittest.TestCase):
    def test_crm_prices_reads_exact_values(self):
        self.assertEqual(probe.crm_prices({"cars": {"UA-0001": {"full": FULL}}}),
                         {"UA-0001": {"ukraine": "21200", "georgia": "17500"}})

    def test_stale_legacy_page_is_flagged(self):
        page = '<div class="cena">19 900 $</div><script type="application/ld+json">{"price":"19900"}</script>'
        result = probe.compare("UA-0001", {"ukraine": "21200"}, probe.page_structure(page))
        self.assertFalse(result["static_matches_crm"])
        self.assertEqual(result["jsonld_prices"], ["19900"])
        self.assertIn("19900", result["static_numbers"])

    def test_current_marker_page_matches(self):
        result = probe.compare("UA-0001", {"ukraine": "21200"}, probe.page_structure(FULL))
        self.assertTrue(result["static_matches_crm"])

    def test_secret_lines_are_masked(self):
        source = "import os\nos.environ['BOT_TOKEN'] = 'x'\nlogin = 'owner@example.com'\n@app.route('/video/<p>')\n"
        lines = probe.redact_lines(source, (r".",))
        self.assertIn("1: import os", lines)
        self.assertIn("2: <REDACTED>", lines)
        self.assertIn("3: <REDACTED>", lines)
        self.assertIn("4: @app.route('/video/<p>')", lines)

    def test_controller_uses_only_get_and_head(self):
        tree = ast.parse((HERE / "controller.py").read_text(encoding="utf-8"))
        methods = {node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and node.value in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}}
        self.assertEqual(methods, {"GET", "HEAD"})


if __name__ == "__main__":
    unittest.main()
