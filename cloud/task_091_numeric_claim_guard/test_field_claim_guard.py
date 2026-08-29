#!/usr/bin/env python3
from __future__ import annotations

import unittest

from field_claim_guard import enforce


class NumericClaimGuardTests(unittest.TestCase):
    def test_reported_regression(self):
        source = "LPG\n1,999cc\n395,459km\nKMHE341DBJA475862"
        parsed = {
            "year": 1999,
            "engine_cc": 1999,
            "mileage_km": 395459,
            "fuel": "LPG",
            "vin": "KMHE341DBJA475862",
        }
        self.assertEqual(enforce(parsed, source), {
            "engine_cc": 1999,
            "mileage_km": 395459,
            "fuel": "LPG",
            "vin": "KMHE341DBJA475862",
        })

    def test_cc_cannot_be_year_even_if_engine_parser_is_absent(self):
        self.assertEqual(enforce({"year": 1999}, "1,999cc"), {})

    def test_km_cannot_be_year_or_engine(self):
        source = "1999km"
        self.assertEqual(
            enforce({"year": 1999, "engine_cc": 1999, "mileage_km": 1999}, source),
            {"mileage_km": 1999},
        )

    def test_bare_year_is_preserved(self):
        self.assertEqual(enforce({"year": 2018}, "2018"), {"year": 2018})

    def test_labeled_year_is_preserved(self):
        self.assertEqual(enforce({"year": 2018}, "Год: 2018"), {"year": 2018})

    def test_same_value_is_allowed_when_independently_repeated(self):
        source = "Год: 1999\nОбъём: 1999cc"
        parsed = {"year": 1999, "engine_cc": 1999}
        self.assertEqual(enforce(parsed, source), parsed)

    def test_liter_engine_conversion(self):
        source = "Двигатель 2.0L"
        parsed = {"year": 2000, "engine_cc": 2000}
        self.assertEqual(enforce(parsed, source), {"engine_cc": 2000})

    def test_price_does_not_become_year(self):
        source = "$1999"
        parsed = {"year": 1999, "price_uah": 1999}
        self.assertEqual(enforce(parsed, source), {"price_uah": 1999})

    def test_vin_digits_are_not_numeric_tokens(self):
        parsed = {"vin": "KMHE341DBJA475862", "year": 2018}
        self.assertEqual(enforce(parsed, "KMHE341DBJA475862"), parsed)

    def test_no_source_preserves_structured_data(self):
        parsed = {"year": 1999, "engine_cc": 1999}
        self.assertEqual(enforce(parsed, ""), parsed)

    def test_non_numeric_fields_are_never_changed(self):
        parsed = {"fuel": "LPG", "model": "K5", "engine_cc": 1999}
        self.assertEqual(enforce(parsed, "LPG\nK5\n1999cc"), parsed)

    def test_one_engine_token_cannot_fill_three_fields(self):
        parsed = {"year": "1999", "engine": "1999", "engine_cc": 1999}
        result = enforce(parsed, "1999 cc")
        self.assertEqual(result, {"engine_cc": 1999})


if __name__ == "__main__":
    unittest.main()
