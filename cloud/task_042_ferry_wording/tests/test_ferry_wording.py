import hashlib
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from ferry_wording import normalize_alias, render, INTERNAL_KEY, contains_forbidden  # noqa: E402
from transform import apply_transform, is_idempotent, protected_markers_preserved  # noqa: E402
import gate_a_preview  # noqa: E402


class TestFerryWordingMapping(unittest.TestCase):
    def test_render_ru(self):
        self.assertEqual(render("sea", "ru", "long"), "На пароме · Корея → Грузия")
        self.assertEqual(render("sea", "ru", "heading"), "На пароме: Корея → Грузия")
        self.assertEqual(render("sea", "ru", "short"), "Паром")

    def test_render_ua(self):
        self.assertEqual(render("sea", "ua", "long"), "На поромі · Корея → Грузія")
        self.assertEqual(render("sea", "ua", "heading"), "На поромі: Корея → Грузія")
        self.assertEqual(render("sea", "ua", "short"), "Пором")

    def test_render_rejects_wrong_key(self):
        with self.assertRaises(ValueError):
            render("customs", "ru", "long")

    def test_legacy_alias_normalizes_to_internal_key(self):
        for alias in ["В море", "в море", "Море", "У морі", "у морі", "На пароме", "На поромі"]:
            self.assertEqual(normalize_alias(alias), INTERNAL_KEY)

    def test_unrelated_text_not_normalized(self):
        self.assertEqual(normalize_alias("Растаможка"), "Растаможка")

    def test_forbidden_detection(self):
        self.assertTrue(contains_forbidden("Текущий статус: В море", "ru"))
        self.assertTrue(contains_forbidden("Море", "ru"))
        self.assertTrue(contains_forbidden("У морі", "ua"))
        self.assertFalse(contains_forbidden("На пароме", "ru"))
        self.assertFalse(contains_forbidden("На поромі", "ua"))


class TestTransform(unittest.TestCase):
    SAMPLES = [
        "В море",
        "В море:",
        "В море ·",
        "Море",
        "У морі",
        "У морі:",
    ]

    def test_transform_removes_forbidden(self):
        for s in self.SAMPLES:
            out = apply_transform(s)
            self.assertNotIn("В море", out)
            self.assertNotIn("У морі", out)

    def test_idempotent(self):
        for s in self.SAMPLES:
            self.assertTrue(is_idempotent(s))

    def test_internal_identifiers_preserved(self):
        html = '<div data-stage="sea"><a href="/catalog?f=sea">В море</a></div>'
        out = apply_transform(html)
        self.assertIn('data-stage="sea"', out)
        self.assertIn("?f=sea", out)
        self.assertNotIn("В море", out)
        self.assertTrue(protected_markers_preserved(html, out))

    def test_legacy_input_alias_documented_intentionally(self):
        # 'before' intentionally contains the forbidden legacy wording as
        # INPUT to the transform (LEGACY_INPUT_ALIAS / HISTORICAL fixture),
        # never as final visible output.
        before = "В море"
        self.assertIn("В море", before)
        after = apply_transform(before)
        self.assertNotIn("В море", after)


class TestGateAPreviewMatrix(unittest.TestCase):
    def setUp(self):
        self.cards = [gate_a_preview.build_preview_for_card(c) for c in gate_a_preview.CARD_IDS]
        self.future = gate_a_preview.build_future_fixtures()

    def test_nine_cards_generated(self):
        self.assertEqual(len(self.cards), 9)
        ids = {c["card_id"] for c in self.cards}
        self.assertEqual(ids, {f"UA-{i:04d}" for i in range(1, 10)})

    def test_cards_no_forbidden_wording_after(self):
        for c in self.cards:
            self.assertFalse(contains_forbidden(c["after"], "ru"))
            self.assertIn('data-stage="sea"', c["after"])
            self.assertIn("?f=sea", c["after"])
            self.assertIn("На пароме", c["after"])
            self.assertIn("Паром", c["after"])

    def test_cards_idempotent(self):
        for c in self.cards:
            self.assertTrue(c["idempotent"])

    def test_future_fixtures_generic_not_hardcoded_to_0009(self):
        ids = {f["card_id"] for f in self.future}
        self.assertTrue(all(cid.startswith("UA-") for cid in ids))
        self.assertFalse(any(cid in {f"UA-{i:04d}" for i in range(1, 10)} for cid in ids))

    def test_future_fixtures_render_new_wording(self):
        for f in self.future:
            self.assertIn("На пароме", f["after"])
            self.assertNotIn("В море", f["after"])
            self.assertIn('data-stage="sea"', f["after"])
            self.assertIn("?f=sea", f["after"])

    def test_no_zero_byte_outputs(self):
        for c in self.cards:
            self.assertGreater(len(c["after"]), 0)
        for f in self.future:
            self.assertGreater(len(f["after"]), 0)

    def test_html_balanced_tags_roughly(self):
        for c in self.cards:
            self.assertEqual(c["after"].count("<div"), c["after"].count("</div>"))


class TestDeterminism(unittest.TestCase):
    def test_ten_builds_byte_identical(self):
        digests = set()
        for _ in range(10):
            cards = [gate_a_preview.build_preview_for_card(c) for c in gate_a_preview.CARD_IDS]
            future = gate_a_preview.build_future_fixtures()
            blob = "".join(c["after"] for c in cards) + "".join(f["after"] for f in future)
            digests.add(hashlib.sha256(blob.encode("utf-8")).hexdigest())
        self.assertEqual(len(digests), 1)


class TestUkrainianNoStaleWording(unittest.TestCase):
    def test_ua_heading_never_stale(self):
        before = "У морі: Корея → Грузія"
        after = apply_transform(before)
        self.assertNotIn("У морі", after)
        self.assertIn("На поромі", after)


if __name__ == "__main__":
    unittest.main()
