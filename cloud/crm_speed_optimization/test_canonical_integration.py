"""TASK 029 identity and monkeypatch integration tests.

These tests prove crm_speed_gate_a.py no longer redefines a duplicate
admin-media transformer/scanner and instead delegates to the canonical
cars_ui_transform module for the actual atomic media-call rewrite.

Run as part of the package-wide discovery command:
    python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cars_ui_transform
import crm_speed_gate_a as gate_a


MEDIA_SOURCE = (
    "def gallery(update, context):\n"
    "    update.message.reply_photo(1)\n"
    "def video_gallery(update, context): pass\n"
    "def diag_photo_show(update, context): pass\n"
    "def diag_video_show(update, context): pass\n"
)


class CanonicalIdentityTests(unittest.TestCase):
    def test_gate_a_module_reference_is_canonical_module_object(self):
        self.assertIs(gate_a.cars_ui_transform, cars_ui_transform)

    def test_no_duplicate_legacy_transformer_class(self):
        self.assertFalse(hasattr(gate_a, "_MediaCallTextTransformer"))

    def test_no_duplicate_legacy_scanner_class(self):
        self.assertFalse(hasattr(gate_a, "_FunctionVisitor"))

    def test_gate_a_transform_delegates_rewrite_to_canonical_function(self):
        with mock.patch.object(
            cars_ui_transform, "transform_cars_ui", wraps=cars_ui_transform.transform_cars_ui
        ) as spy:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        spy.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertIn("reply_text", result["candidate"])
        self.assertNotIn("reply_photo(", result["candidate"])

    def test_gate_a_transform_does_not_call_canonical_when_no_rewrite_needed(self):
        clean_source = (
            "def gallery(update, context): pass\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        with mock.patch.object(
            cars_ui_transform, "transform_cars_ui", wraps=cars_ui_transform.transform_cars_ui
        ) as spy:
            result = gate_a.transform_cars_ui(clean_source)
        spy.assert_not_called()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["candidate"], clean_source)


class CanonicalMonkeypatchTests(unittest.TestCase):
    def test_gate_a_surfaces_canonical_blocked_reason(self):
        stub_result = {"status": "BLOCKED", "reason": "stubbed_block_for_test", "candidate": None}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result) as stub:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        stub.assert_called_once()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("stubbed_block_for_test", result["reasons"])
        self.assertIsNone(result["candidate"])

    def test_gate_a_surfaces_canonical_ok_candidate_unmodified(self):
        stub_candidate = (
            "def gallery(update, context):\n"
            "    update.message.reply_text('[stubbed]')\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        stub_result = {"status": "OK", "reason": "rewritten", "candidate": stub_candidate}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result) as stub:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        stub.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["candidate"], stub_candidate)

    def test_gate_a_rejects_canonical_result_that_reintroduces_violation(self):
        # Canonical layer claims OK but returns a candidate that still
        # contains a direct media call (simulated canonical bug); the
        # gate_a adapter's post-rewrite re-scan must still fail closed.
        stub_candidate = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(1)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        stub_result = {"status": "OK", "reason": "rewritten", "candidate": stub_candidate}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result):
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])


if __name__ == "__main__":
    unittest.main()
