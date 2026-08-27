import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import transform  # noqa: E402


class TestMappings(unittest.TestCase):
    def test_ru_status(self):
        html = '<span class="status-pill">В море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, '<span class="status-pill">На пароме</span>')
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0]["classification"], "USER_FACING_STATUS")
        self.assertEqual(occ[0]["language"], "ru")

    def test_uk_status(self):
        html = '<span class="status-pill">У морі</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, '<span class="status-pill">На поромі</span>')
        self.assertEqual(occ[0]["language"], "uk")

    def test_ru_long(self):
        html = '<div class="route-long">В море · Корея → Грузия</div>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<div class="route-long">На пароме · Корея → Грузия</div>')

    def test_uk_long(self):
        html = '<div class="route-long">У морі · Корея → Грузія</div>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<div class="route-long">На поромі · Корея → Грузія</div>')

    def test_ru_heading(self):
        html = '<h2 class="route-heading">В море: Корея → Грузия</h2>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<h2 class="route-heading">На пароме: Корея → Грузия</h2>')

    def test_uk_heading(self):
        html = '<h2 class="route-heading">У морі: Корея → Грузія</h2>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<h2 class="route-heading">На поромі: Корея → Грузія</h2>')

    def test_short_ru(self):
        html = '<span class="stage-step" data-lang="ru">Море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, '<span class="stage-step" data-lang="ru">Паром</span>')
        self.assertEqual(occ[0]["classification"], "USER_FACING_SHORT_STAGE")

    def test_short_uk(self):
        html = '<span class="stage-step" data-lang="uk">Море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, '<span class="stage-step" data-lang="uk">Пором</span>')

    def test_short_ambiguous_without_lang(self):
        html = '<span class="stage-step">Море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ[0]["classification"], "AMBIGUOUS")

    def test_ambiguous_short_never_becomes_parom(self):
        html = '<span class="stage-step">Море</span>'
        out, _ = transform.transform_document(html)
        self.assertNotIn("Паром", out)
        self.assertNotIn("Пором", out)

    def test_data_ru_and_data_uk_together(self):
        html = ('<div data-ru="В море · Корея → Грузия" '
                'data-uk="У морі · Корея → Грузія"></div>')
        out, occ = transform.transform_document(html)
        self.assertIn('data-ru="На пароме · Корея → Грузия"', out)
        self.assertIn('data-uk="На поромі · Корея → Грузія"', out)
        self.assertEqual(len(occ), 2)

    def test_previously_failing_span_status_pill(self):
        html = '<span class="status-pill">В море</span>'
        out, _ = transform.transform_document(html)
        self.assertNotIn("В море", out)
        self.assertIn("На пароме", out)

    def test_nested_elements(self):
        html = ('<div class="card"><div class="status-pill">'
                '<span>В море</span></div></div>')
        out, occ = transform.transform_document(html)
        self.assertIn("На пароме", out)
        self.assertEqual(len(occ), 1)


class TestOrdinaryProseUnchanged(unittest.TestCase):
    def test_prose_car_in_sea(self):
        html = '<p>Автомобиль в море уже 20 дней</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_prose_sea_worries(self):
        html = '<p>Море волнуется, паром в порту</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_prose_rest_at_sea(self):
        html = '<p>Отдых на море</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])


class TestScriptStyleCommentLegacy(unittest.TestCase):
    def test_script_untouched(self):
        html = '<script>var s="В море";</script>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_style_untouched(self):
        html = '<style>.x::before{content:"В море"}</style>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)

    def test_comment_untouched(self):
        html = '<!-- В море -->'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_legacy_alias_untouched(self):
        html = '<span class="status-pill" data-legacy-alias="В море">В море</span>'
        out, occ = transform.transform_document(html)
        self.assertIn('data-legacy-alias="В море"', out)
        self.assertIn("На пароме", out)


class TestStructuralPreservation(unittest.TestCase):
    def test_internal_markers_untouched(self):
        html = ('<a href="?f=sea" id="stage-sea-1" data-stage="sea" '
                'class="status-pill">В море</a>')
        out, _ = transform.transform_document(html)
        self.assertIn('href="?f=sea"', out)
        self.assertIn('id="stage-sea-1"', out)
        self.assertIn('data-stage="sea"', out)
        self.assertIn("На пароме", out)

    def test_quote_variants(self):
        html_double = '<div data-ru="В море"></div>'
        html_single = "<div data-ru='В море'></div>"
        out_d, _ = transform.transform_document(html_double)
        out_s, _ = transform.transform_document(html_single)
        self.assertIn('data-ru="На пароме"', out_d)
        self.assertIn("data-ru='На пароме'", out_s)

    def test_void_elements_preserved(self):
        html = '<span class="status-pill">В море<br>текст</span>'
        out, _ = transform.transform_document(html)
        self.assertIn("<br>", out)

    def test_uppercase_tags_preserved(self):
        html = '<SPAN CLASS="status-pill">В море</SPAN>'
        out, _ = transform.transform_document(html)
        self.assertTrue(out.startswith("<SPAN"))
        self.assertTrue(out.endswith("</SPAN>"))
        self.assertIn("На пароме", out)

    def test_entity_preserved(self):
        html = '<span class="status-pill">В&nbsp;море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])


class TestDeterminismAndIdempotence(unittest.TestCase):
    SAMPLE = ('<div class="status-pill">В море</div>'
              '<div class="route-long">У морі · Корея → Грузія</div>'
              '<span class="stage-step" data-lang="ru">Море</span>')

    def test_ten_run_determinism(self):
        first, _ = transform.transform_document(self.SAMPLE)
        for _ in range(10):
            out, _ = transform.transform_document(self.SAMPLE)
            self.assertEqual(out, first)

    def test_idempotence(self):
        once, _ = transform.transform_document(self.SAMPLE)
        twice, _ = transform.transform_document(once)
        self.assertEqual(once, twice)


class TestCompiles(unittest.TestCase):
    def test_module_compiles(self):
        import py_compile
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        py_compile.compile(os.path.join(here, "transform.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
