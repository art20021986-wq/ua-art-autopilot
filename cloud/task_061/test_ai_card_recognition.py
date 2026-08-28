"""
Offline deterministic tests for TASK 061 CRM-AI-CARD-001.
Run with: python3 -m pytest cloud/task_061/test_ai_card_recognition.py -v
or:       python3 cloud/task_061/test_ai_card_recognition.py

These tests exercise only the new local module; no network, no CRM db,
no model tokens.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from ai_card_recognition import recognize  # noqa: E402

ACCEPTANCE_TEXT = (
    "Kia K5 2018\nVIN KNAGU416BKA324445\n198000 km\nLPG\n2000 cc\nautomatic"
)

LIVE_ALLOWED = {
    "brand", "model", "year", "vin", "mileage", "fuel_type",
    "engine_cc", "transmission",
}


class TestAcceptanceCase(unittest.TestCase):
    def test_full_acceptance_case(self):
        result = recognize(ACCEPTANCE_TEXT, LIVE_ALLOWED)
        self.assertEqual(result.get("brand"), "Kia")
        self.assertEqual(result.get("model"), "K5")
        self.assertEqual(result.get("year"), "2018")
        self.assertEqual(result.get("vin"), "KNAGU416BKA324445")
        self.assertEqual(result.get("mileage"), "198000")
        self.assertEqual(result.get("fuel_type"), "LPG")
        self.assertEqual(result.get("engine_cc"), "2000")
        self.assertEqual(result.get("transmission"), "Автомат")

    def test_filters_unknown_keys(self):
        narrow_allowed = {"vin", "year"}
        result = recognize(ACCEPTANCE_TEXT, narrow_allowed)
        self.assertEqual(set(result.keys()), {"vin", "year"})

    def test_partial_recognition_no_invention(self):
        result = recognize("just some random text with no fields", LIVE_ALLOWED)
        self.assertEqual(result, {})

    def test_partial_only_vin(self):
        result = recognize("random note VIN KNAGU416BKA324445 end", LIVE_ALLOWED)
        self.assertEqual(result, {"vin": "KNAGU416BKA324445"})

    def test_empty_text(self):
        self.assertEqual(recognize("", LIVE_ALLOWED), {})
        self.assertEqual(recognize(None, LIVE_ALLOWED), {})


if __name__ == "__main__":
    unittest.main()
