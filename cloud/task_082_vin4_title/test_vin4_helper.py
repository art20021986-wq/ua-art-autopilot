"""Deterministic offline tests for vin4_helper. No network, no DB, no LLM.

Run: python3 -m pytest cloud/task_082_vin4_title/test_vin4_helper.py -q
or:  python3 cloud/task_082_vin4_title/test_vin4_helper.py
"""
import re
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import vin4_helper as v4  # noqa: E402

VALID_VIN_DIGITS_END = "1HGCM82633A004352"      # ends in digits
VALID_VIN_LETTERS_END = "1HGCM82633A00435X"      # ends in a letter (last char X)
VALID_VIN_LOWERCASE = "1hgcm82633a004352"
VALID_VIN_SPACED = "1HG CM8-2633A00 4352"
INVALID_VIN_SHORT = "1HGCM82633A0043"
INVALID_VIN_BADCHARS = "1HGCM82633AOOI352"  # contains letters I,O not allowed


class TestNormalize(unittest.TestCase):
    def test_normalize_strip_upper(self):
        self.assertEqual(v4.normalize_vin("  1hgcm82633a004352  "), "1HGCM82633A004352")

    def test_normalize_removes_spaces_dashes(self):
        self.assertEqual(v4.normalize_vin(VALID_VIN_SPACED), "1HGCM82633A004352")

    def test_normalize_none(self):
        self.assertEqual(v4.normalize_vin(None), "")


class TestValidity(unittest.TestCase):
    def test_valid_17_chars(self):
        self.assertTrue(v4.is_valid_vin(VALID_VIN_DIGITS_END))

    def test_invalid_short(self):
        self.assertFalse(v4.is_valid_vin(INVALID_VIN_SHORT))

    def test_invalid_bad_chars(self):
        self.assertFalse(v4.is_valid_vin(INVALID_VIN_BADCHARS))


class TestGetVin4(unittest.TestCase):
    def test_digits_end(self):
        self.assertEqual(v4.get_vin4(VALID_VIN_DIGITS_END), "4352")

    def test_letters_end(self):
        self.assertEqual(v4.get_vin4(VALID_VIN_LETTERS_END), "435X")

    def test_lowercase(self):
        self.assertEqual(v4.get_vin4(VALID_VIN_LOWERCASE), "4352")

    def test_spaced_dashed(self):
        self.assertEqual(v4.get_vin4(VALID_VIN_SPACED), "4352")

    def test_missing_returns_none(self):
        self.assertIsNone(v4.get_vin4(None))
        self.assertIsNone(v4.get_vin4(""))

    def test_invalid_returns_none(self):
        self.assertIsNone(v4.get_vin4(INVALID_VIN_SHORT))
        self.assertIsNone(v4.get_vin4(INVALID_VIN_BADCHARS))


class TestRenderTitleHtml(unittest.TestCase):
    def test_valid_vin_exact_format(self):
        out = v4.render_title_html("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        self.assertEqual(out, "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN <b>4352</b>")

    def test_missing_vin_bold_marker(self):
        out = v4.render_title_html("UA-0099", "Toyota", "Camry", 2020, None)
        self.assertEqual(out, "UA-0099 · Toyota Camry 2020 · <b>VIN НЕТ</b>")

    def test_exactly_one_bold_tag_pair(self):
        out = v4.render_title_html("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        self.assertEqual(out.count("<b>"), 1)
        self.assertEqual(out.count("</b>"), 1)

    def test_html_escaping_of_brand_model(self):
        out = v4.render_title_html("UA-0001", "<script>alert(1)</script>", "X", 2019, VALID_VIN_DIGITS_END)
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_idempotent_no_double_suffix(self):
        first = v4.render_title_html("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        second = v4.render_title_html("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END, existing_title=first)
        self.assertEqual(second, first)
        self.assertEqual(second.count("VIN"), 1)


class TestRenderButtonLabel(unittest.TestCase):
    def test_valid_vin_no_markup(self):
        out = v4.render_button_label("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        self.assertEqual(out, "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN 4352")
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)

    def test_missing_vin_plain_marker(self):
        out = v4.render_button_label("UA-0099", "Toyota", "Camry", 2020, None)
        self.assertEqual(out, "UA-0099 · Toyota Camry 2020 · VIN НЕТ")

    def test_exactly_one_vin_token(self):
        out = v4.render_button_label("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        self.assertEqual(len(re.findall(r"VIN", out)), 1)

    def test_idempotent_no_double_suffix(self):
        first = v4.render_button_label("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END)
        second = v4.render_button_label("UA-0013", "Mercedes-Benz", "Б-КЛАССА", 2015, VALID_VIN_DIGITS_END, existing_label=first)
        self.assertEqual(second, first)

    def test_telegram_length_limit_truncation(self):
        long_brand = "A" * 200
        out = v4.render_button_label("UA-0001", long_brand, "Model", 2020, VALID_VIN_DIGITS_END)
        self.assertLessEqual(len(out), v4.BUTTON_MAX_LEN)
        self.assertTrue(out.endswith("…") or "VIN" in out)


class TestFutureFixtureUA9999(unittest.TestCase):
    def test_future_car_covered_automatically(self):
        out = v4.render_title_html("UA-9999", "Skoda", "Octavia", 2024, VALID_VIN_LETTERS_END)
        self.assertEqual(out, "UA-9999 · Skoda Octavia 2024 · VIN <b>435X</b>")
        btn = v4.render_button_label("UA-9999", "Skoda", "Octavia", 2024, VALID_VIN_LETTERS_END)
        self.assertEqual(btn, "UA-9999 · Skoda Octavia 2024 · VIN 435X")


class TestNoFullVinLeak(unittest.TestCase):
    def test_full_vin_never_appears_in_output(self):
        out_title = v4.render_title_html("UA-0001", "Toyota", "Camry", 2020, VALID_VIN_DIGITS_END)
        out_btn = v4.render_button_label("UA-0001", "Toyota", "Camry", 2020, VALID_VIN_DIGITS_END)
        self.assertNotIn(VALID_VIN_DIGITS_END, out_title)
        self.assertNotIn(VALID_VIN_DIGITS_END, out_btn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
