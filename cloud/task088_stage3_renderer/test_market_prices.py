import copy
from decimal import Decimal
from html.parser import HTMLParser
from html import unescape
import re
import unittest

from uaart_market_prices import CAPTIONS, END, START, normalized_usd, render_market_prices


def visible_lines(fragment):
    """Read each rendered price heading independently of its HTML wrappers."""
    return [unescape(re.sub(r"<[^>]+>", "", line)) for line in re.findall(
        r'<div class="ua-market-amount-v1"[^>]*>(.*?)</div>', fragment)]


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

    def test_card_and_catalog_share_exact_values_with_captions_only_on_full_card(self):
        row = {"price_uah": 9000, "price_georgia": 7000}
        full = render_market_prices(row)
        compact = render_market_prices(row, compact=True)
        price_data = lambda fragment: [{key: value for key, value in attrs.items() if key.startswith("data-ua-")}
                                       for attrs in Parsed(fragment).markets]
        self.assertEqual(price_data(full), price_data(compact))
        self.assertEqual(visible_lines(full), visible_lines(compact))
        self.assertNotIn("ua-market-caption-v1", compact)
        for caption in CAPTIONS.values():
            for text in caption.values():
                self.assertIn(text, full)
                self.assertNotIn(text, compact)

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

    def test_final_v5_exact_country_price_lines_and_full_captions(self):
        row = {"price_uah": 24500, "price_georgia": 18900}
        for compact in (False, True):
            with self.subTest(compact=compact):
                fragment = render_market_prices(row, compact=compact)
                self.assertEqual(visible_lines(fragment), [
                    "🇺🇦 Украина — 24 500 $", "🇬🇪 Грузия — 18 900 $"])
                self.assertNotIn("AUTOPAPA", fragment)
                self.assertNotIn("без растаможки", fragment)
        self.assertEqual(CAPTIONS["ukraine"]["ru"],
                         "Цена с доставкой в Киев с растаможкой и сертификацией")
        self.assertEqual(CAPTIONS["georgia"]["ru"],
                         "Цена автомобиля с доставкой до авторынка Рустави 🅿️ №16")

    def test_final_v5_missing_georgia_is_labelled_without_zero_amount(self):
        for compact in (False, True):
            fragment = render_market_prices({"price_uah": 24500, "price_georgia": None}, compact=compact)
            self.assertEqual(visible_lines(fragment), [
                "🇺🇦 Украина — 24 500 $", "🇬🇪 Грузия — Цена уточняется"])
            self.assertNotIn("Грузия — 0 $", "".join(visible_lines(fragment)))

    def test_final_v5_translation_attributes_preserve_numeric_values(self):
        # Static attribute contract only. The real site's language scripts and
        # browser switching remain separate, required integration evidence.
        labels = {
            "ru": ("Украина", "Грузия", "Цена уточняется"),
            "uk": ("Україна", "Грузія", "Ціна уточнюється"),
            "ua": ("Україна", "Грузія", "Ціна уточнюється"),
            "ka": ("უკრაინა", "საქართველო", "ფასი ზუსტდება"),
            "ge": ("უკრაინა", "საქართველო", "ფასი ზუსტდება"),
        }
        for compact in (False, True):
            for ge_price in (18900, None):
                original = render_market_prices({"price_uah": 24500, "price_georgia": ge_price}, compact=compact)
                before_values = Parsed(original).markets
                for language, (ua, ge, missing) in labels.items():
                    def translate(match):
                        attributes, default = match.groups()
                        selected = re.search(r'\bdata-' + language + r'="([^"]*)"', attributes)
                        return '<span' + attributes + '>' + (selected.group(1) if selected else default) + '</span>'
                    translated = re.sub(r'<span([^>]*)>([^<]*)</span>', translate, original)
                    expected_ge = "18 900 $" if ge_price is not None else missing
                    self.assertEqual(visible_lines(translated), [
                        "🇺🇦 " + ua + " — 24 500 $", "🇬🇪 " + ge + " — " + expected_ge])
                    self.assertEqual(Parsed(translated).markets, before_values)


if __name__ == "__main__":
    unittest.main()
