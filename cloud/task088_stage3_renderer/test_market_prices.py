import copy
from decimal import Decimal
from html.parser import HTMLParser
import importlib.util
import pathlib
import unittest

from uaart_market_prices import CAPTIONS, END, START, normalized_usd, render_market_prices


class Parsed(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.markets = []
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if "data-ua-market" in attrs:
            self.markets.append(attrs)


class MarketPricesTest(unittest.TestCase):
    def test_two_independent_usd_prices_in_order(self):
        parsed = Parsed(render_market_prices({"price_uah": 12000, "price_georgia": 7800}))
        self.assertEqual([m["data-ua-market"] for m in parsed.markets], ["ukraine", "georgia"])
        self.assertEqual([m["data-ua-field"] for m in parsed.markets], ["price_uah", "price_georgia"])
        self.assertEqual([m["data-ua-value"] for m in parsed.markets], ["12000", "7800"])
        self.assertEqual([m["data-ua-currency"] for m in parsed.markets], ["USD", "USD"])

    def test_missing_georgia_remains_visible(self):
        for absent in (None, "", "   ", 0, 0.0, "0", "0.00"):
            with self.subTest(absent=absent):
                out = render_market_prices({"price_uah": 12000, "price_georgia": absent})
                self.assertIn("Цена уточняется", out)
                self.assertIn(CAPTIONS["georgia"]["ru"], out)
                self.assertEqual(Parsed(out).markets[1]["data-ua-value"], "")

    def test_independence_in_both_directions(self):
        row = {"price_uah": "12999", "price_georgia": "8123"}
        before = Parsed(render_market_prices(row)).markets
        for field, change_index, other_index in (("price_uah", 0, 1), ("price_georgia", 1, 0)):
            changed = dict(row, **{field: "9999"})
            after = Parsed(render_market_prices(changed)).markets
            self.assertEqual(before[other_index], after[other_index])
            self.assertNotEqual(before[change_index], after[change_index])

    def test_input_model_never_mutated(self):
        row = {"price_uah": 11000, "price_georgia": 9000, "photos": ["photo.jpg"], "nested": {"a": 1}}
        original = copy.deepcopy(row)
        render_market_prices(row)
        self.assertEqual(row, original)

    def test_usd_values_are_not_converted_or_rounded(self):
        for value, expected in (("8500.01", "8500.01"), (8500.25, "8500.25"), (Decimal("8500.10"), "8500.1"), ("0008500.00", "8500")):
            self.assertEqual(normalized_usd(value), expected)
        self.assertIn("8 500.01 $", render_market_prices({"price_uah": "8500.01"}))

    def test_invalid_values_block_instead_of_inventing_prices(self):
        for value in (-1, True, False, [], {}, "<script>1</script>", "1,20", "NaN", float("inf"), "100.001", "1e4", "8500 UAH", "-0"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    render_market_prices({"price_uah": 9000, "price_georgia": value})

    def test_legacy_ukraine_fallback_requires_reconciliation(self):
        for value in (None, 0, ""):
            row = {"price_uah": value, "price_georgia": 7000, "price_total": 8500}
            before = dict(row)
            with self.assertRaisesRegex(ValueError, "LEGACY_UA_PRICE_FALLBACK_REQUIRES_RECONCILIATION"):
                render_market_prices(row)
            self.assertEqual(row, before)
        out = render_market_prices({"price_uah": 9000, "price_georgia": 7000, "price_total": 8500})
        self.assertEqual(Parsed(out).markets[0]["data-ua-value"], "9000")

    def test_supported_language_attributes_preserved(self):
        out = render_market_prices({"price_uah": 8500})
        for attribute in ("data-ru", "data-ua", "data-uk", "data-ge", "data-ka"):
            self.assertIn(attribute + '="', out)
        for market in CAPTIONS.values():
            for text in market.values():
                self.assertIn(text, out)

    def test_no_global_styles_scripts_or_navigation(self):
        parsed = Parsed(render_market_prices({"price_uah": 9000}))
        self.assertEqual(set(parsed.tags), {"div", "span"})
        self.assertNotIn("под ключ", render_market_prices({"price_uah": 9000}).lower())
        self.assertNotIn("доплат нет", render_market_prices({"price_uah": 9000}).lower())

    def test_card_and_catalog_share_exact_values_and_captions(self):
        row = {"price_uah": 9000, "price_georgia": 7000}
        self.assertEqual(Parsed(render_market_prices(row)).markets, Parsed(render_market_prices(row, compact=True)).markets)
        for caption in CAPTIONS.values():
            for text in caption.values():
                self.assertIn(text, render_market_prices(row, compact=True))

    def test_exact_component_boundaries(self):
        out = render_market_prices({})
        self.assertTrue(out.startswith(START))
        self.assertTrue(out.endswith(END))
        self.assertEqual(out.count(START), 1)
        self.assertEqual(out.count(END), 1)

    def test_live_component_requires_exact_car_identity(self):
        for car_id in (None, "", "UA-10", "UA-0010<script>", "UA-0010 ", 10):
            with self.assertRaisesRegex(ValueError, "PRICE_COMPONENT_CAR_ID_INVALID"):
                render_market_prices({"auto_number": car_id, "price_uah": 9000}, require_car_id=True)
        out = render_market_prices({"auto_number": "UA-0010", "price_uah": 9000}, require_car_id=True)
        self.assertIn('data-ua-car="UA-0010"', out)

    def test_captions_match_approved_owner_policy(self):
        policy = pathlib.Path(__file__).resolve().parents[1] / "task088_autopilot_owner_policy" / "price_captions.py"
        spec = importlib.util.spec_from_file_location("owner_captions", policy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for market in ("ukraine", "georgia"):
            for language in ("ru", "uk"):
                self.assertEqual(CAPTIONS[market][language], module.price_caption(market, language))


if __name__ == "__main__":
    unittest.main()
