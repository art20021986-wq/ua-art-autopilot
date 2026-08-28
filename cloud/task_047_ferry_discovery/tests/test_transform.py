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


class TestFerryPhase1RealContexts(unittest.TestCase):
    def test_audit_mixed_case_prose_is_unchanged(self):
        html = '<p>Автомобиль В море уже 20 дней</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_longer_prose_in_data_attribute_is_unchanged(self):
        html = '<p data-ru="В море уже 20 дней" data-uk="У морі вже 20 днів">текст</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_longer_prose_in_status_class_is_unchanged(self):
        html = '<p class="status-pill">В море уже 20 дней</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_script_with_tag_looking_string_is_opaque(self):
        html = '<script>const x="<span>В море</span>";</script><p>ok</p>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_audit_bilingual_attributes_and_visible_text(self):
        html = '<div class="status-pill" data-ru="В море" data-uk="У морі">В море</div>'
        out, occ = transform.transform_document(html)
        self.assertEqual(
            out,
            '<div class="status-pill" data-ru="На пароме" data-uk="На поромі">На пароме</div>',
        )
        self.assertEqual(len(occ), 3)

    def test_real_bilingual_long_attributes(self):
        html = (
            '<div class="status-pill" data-ru="В море · Корея → Грузия" '
            'data-uk="У морі · Корея → Грузія">В море · Корея → Грузия</div>'
        )
        out, occ = transform.transform_document(html)
        self.assertIn('data-ru="На пароме · Корея → Грузия"', out)
        self.assertIn('data-uk="На поромі · Корея → Грузія"', out)
        self.assertIn('>На пароме · Корея → Грузия</div>', out)
        self.assertEqual(len(occ), 3)

    def test_four_sibling_spans(self):
        html = (
            '<div style="display:flex"><span>Корея</span><span>Море</span>'
            '<span>Грузия</span><span>Киев</span></div>'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(
            out,
            '<div style="display:flex"><span>Корея</span><span>Паром</span>'
            '<span>Грузия</span><span>Киев</span></div>',
        )
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0]["context"], "FOUR_SPAN_SEQUENCE")

    def test_four_span_markup_inside_script_is_unchanged(self):
        html = (
            '<script>const x="<span>Корея</span><span>Море</span>'
            '<span>Грузия</span><span>Киев</span>";</script>'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_four_span_markup_inside_unclosed_script_is_unchanged(self):
        html = (
            '<script>const x="<span>Корея</span><span>Море</span>'
            '<span>Грузия</span><span>Киев</span>";'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_four_span_markup_in_legacy_attribute_is_unchanged(self):
        html = (
            '<div data-template="&lt;span&gt;Корея&lt;/span&gt;'
            '&lt;span&gt;Море&lt;/span&gt;&lt;span&gt;Грузия&lt;/span&gt;'
            '&lt;span&gt;Киев&lt;/span&gt;">ok</div>'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ, [])

    def test_four_span_out_of_order_is_ambiguous_not_rewritten(self):
        html = (
            '<div><span>Корея</span><span>Море</span>'
            '<span>Киев</span><span>Грузия</span></div>'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0]["classification"], "AMBIGUOUS")

    def test_chip_short_word_defaults_to_ru(self):
        html = '<div class="chip">Море</div>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<div class="chip">Паром</div>')

    def test_etap_route_heading(self):
        html = '<div class="etap tut"><div class="krug">3</div>Море: Корея → Грузия</div>'
        out, _ = transform.transform_document(html)
        self.assertEqual(
            out,
            '<div class="etap tut"><div class="krug">3</div>Паром: Корея → Грузия</div>',
        )

    def test_info_exact_phrase(self):
        html = '<p>Море Корея → Грузия — около 60 дней</p>'
        out, _ = transform.transform_document(html)
        self.assertEqual(out, '<p>Паром Корея → Грузия — около 60 дней</p>')

    def test_bare_status_is_ambiguous(self):
        html = '<span>В море</span>'
        out, occ = transform.transform_document(html)
        self.assertEqual(out, html)
        self.assertEqual(occ[0]["classification"], "AMBIGUOUS")

    def test_new_contexts_are_idempotent(self):
        html = (
            '<div class="chip">В море</div>'
            '<div><span>Корея</span><span>Море</span><span>Грузия</span><span>Киев</span></div>'
        )
        once, _ = transform.transform_document(html)
        twice, second_occ = transform.transform_document(once)
        self.assertEqual(once, twice)
        self.assertEqual(second_occ, [])


class TestCatalogSeaTwoLine(unittest.TestCase):
    def test_sea_card_route_is_two_lines_in_both_languages(self):
        html = (
            '<article class="catalog-card" data-stage="sea">'
            '<div class="status-pill" data-ru="В море · Корея → Грузия" '
            'data-uk="У морі · Корея → Грузія">В море · Корея → Грузия</div>'
            '</article>'
        )
        out, occ = transform.transform_document(html)
        self.assertIn('data-ru="На пароме&#10;Маршрут: Корея → Грузия"', out)
        self.assertIn('data-uk="На поромі&#10;Маршрут: Корея → Грузія"', out)
        self.assertIn('>На пароме&#10;Маршрут: Корея → Грузия</div>', out)
        self.assertIn('style="white-space:pre-line"', out)
        self.assertEqual(len(occ), 3)
        self.assertTrue(all(
            item["classification"] == "USER_FACING_CATALOG_ROUTE" for item in occ
        ))

    def test_accepted_one_line_candidate_advances_to_two_lines(self):
        html = (
            '<article class="catalog-card" data-stage="sea">'
            '<div class="status-pill" data-ru="На пароме · Корея → Грузия" '
            'data-uk="На поромі · Корея → Грузія">На пароме · Корея → Грузия</div>'
            '</article>'
        )
        out, _ = transform.transform_document(html)
        self.assertEqual(out.count("&#10;Маршрут:"), 3)

    def test_non_sea_card_keeps_single_line_contract(self):
        html = (
            '<article class="catalog-card" data-stage="kiev">'
            '<div class="status-pill">В море · Корея → Грузия</div>'
            '</article>'
        )
        out, _ = transform.transform_document(html)
        self.assertIn('>На пароме · Корея → Грузия</div>', out)
        self.assertNotIn("&#10;Маршрут:", out)
        self.assertNotIn("white-space:pre-line", out)

    def test_sea_filter_visible_counter_is_updated(self):
        html = (
            '<button data-f="sea" data-ru="В море · 4" '
            'data-uk="У морі · 4">В море · 4</button>'
        )
        out, occ = transform.transform_document(html)
        self.assertEqual(
            out,
            '<button data-f="sea" data-ru="На пароме · 4" '
            'data-uk="На поромі · 4">На пароме · 4</button>',
        )
        self.assertEqual(len(occ), 3)

    def test_future_sea_card_and_style_are_idempotent(self):
        html = (
            '<article class="catalog-card" data-stage="sea"><span>UA-0042</span>'
            '<div class="status-pill" style="color:#fff" '
            'data-ru="В море · Корея → Грузия" '
            'data-uk="У морі · Корея → Грузія">В море · Корея → Грузия</div>'
            '</article>'
        )
        once, _ = transform.transform_document(html)
        twice, second_occ = transform.transform_document(once)
        self.assertIn('style="color:#fff;white-space:pre-line"', once)
        self.assertEqual(once, twice)
        self.assertEqual(second_occ, [])

    def test_static_catalog_result_uses_actual_card_count(self):
        cards = "".join(
            '<article class="catalog-card" data-stage="kiev">UA-%04d</article>' % number
            for number in range(1, 11)
        )
        html = '<p class="catalog-result">Показано: 8</p>' + cards
        out, occ = transform.transform_document(html)
        self.assertIn('<p class="catalog-result">Показано: 10</p>', out)
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0]["classification"], "USER_FACING_CATALOG_COUNT")


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
