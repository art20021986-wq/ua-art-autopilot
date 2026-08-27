import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from transform import apply_transform, transform_html, classify_text


class TestApplyTransformPlainText(unittest.TestCase):
    def test_ordinary_prose_car_in_sea_unchanged(self):
        text = "Автомобиль в море уже 20 дней"
        self.assertEqual(apply_transform(text, lang="ru"), text)

    def test_ordinary_prose_sea_is_rough_unchanged(self):
        text = "Море волнуется, паром в порту"
        self.assertEqual(apply_transform(text, lang="ru"), text)

    def test_ordinary_prose_rest_at_sea_unchanged(self):
        text = "Отдых на море"
        self.assertEqual(apply_transform(text, lang="ru"), text)

    def test_exact_short_label_ru(self):
        self.assertEqual(apply_transform("В море", lang="ru"), "Паром")

    def test_exact_short_label_uk(self):
        self.assertEqual(apply_transform("У морі", lang="uk"), "Пором")

    def test_exact_status_with_route_ru(self):
        self.assertEqual(
            apply_transform("В море · Корея → Грузия", lang="ru"),
            "На пароме · Корея → Грузия",
        )

    def test_exact_status_colon_form_ru(self):
        self.assertEqual(
            apply_transform("В море: Корея → Грузия", lang="ru"),
            "На пароме: Корея → Грузия",
        )

    def test_preserves_surrounding_whitespace(self):
        self.assertEqual(apply_transform("  В море  ", lang="ru"), "  Паром  ")

    def test_classify_short_stage(self):
        self.assertEqual(classify_text("В море"), "USER_FACING_SHORT_STAGE")

    def test_classify_status(self):
        self.assertEqual(classify_text("В море · Корея → Грузия"), "USER_FACING_STATUS")

    def test_classify_ordinary_prose(self):
        self.assertEqual(classify_text("Автомобиль в море уже 20 дней"), "ORDINARY_PROSE")


class TestTransformHtml(unittest.TestCase):
    def test_script_body_untouched(self):
        html = '<script>const legacy = "В море";</script>'
        new_html, occ = transform_html(html, lang="ru")
        self.assertEqual(new_html, html)
        self.assertEqual(occ, [])

    def test_style_body_untouched(self):
        html = '<style>.sea{content:"В море"}</style>'
        new_html, occ = transform_html(html, lang="ru")
        self.assertEqual(new_html, html)

    def test_visible_text_node_replaced(self):
        html = '<span class="status">В море</span>'
        new_html, occ = transform_html(html, lang="ru")
        self.assertEqual(new_html, '<span class="status">Паром</span>')
        self.assertEqual(len(occ), 1)

    def test_approved_attribute_replaced(self):
        html = '<span data-ru="В море" data-stage="sea">x</span>'
        new_html, occ = transform_html(html, lang="ru")
        self.assertIn('data-ru="Паром"', new_html)
        self.assertIn('data-stage="sea"', new_html)

    def test_internal_stage_marker_untouched(self):
        html = '<div data-stage="sea" class="card">В море</div>'
        new_html, occ = transform_html(html, lang="ru")
        self.assertIn('data-stage="sea"', new_html)
        self.assertIn(">Паром<", new_html)

    def test_ordinary_prose_inside_paragraph_unchanged(self):
        html = "<p>Автомобиль в море уже 20 дней</p>"
        new_html, occ = transform_html(html, lang="ru")
        self.assertEqual(new_html, html)
        self.assertEqual(occ, [])

    def test_uk_route_form(self):
        html = '<span>У морі · Корея → Грузія</span>'
        new_html, occ = transform_html(html, lang="uk")
        self.assertEqual(new_html, '<span>На поромі · Корея → Грузія</span>')

    def test_determinism_10_runs(self):
        html = '<span data-ru="В море">В море</span><script>const legacy="В море";</script>'
        outputs = set()
        for _ in range(10):
            new_html, _ = transform_html(html, lang="ru")
            outputs.add(new_html)
        self.assertEqual(len(outputs), 1)
        self.assertIn('legacy="В море"', list(outputs)[0])


if __name__ == "__main__":
    unittest.main()
