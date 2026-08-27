import unittest

import transform

RU_STATUS = "\u0412 \u043c\u043e\u0440\u0435"          # "\u0412 \u043c\u043e\u0440\u0435"
RU_STATUS_NEW = "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435"
UK_STATUS = "\u0423 \u043c\u043e\u0440\u0456"
UK_STATUS_NEW = "\u041d\u0430 \u043f\u043e\u0440\u043e\u043c\u0456"
SHORT_RU = "\u041c\u043e\u0440\u0435"
SHORT_RU_NEW = "\u041f\u0430\u0440\u043e\u043c"


class TransformBaselineTests(unittest.TestCase):

    def test_ordinary_prose_preserved(self):
        html = f"<p>\u0410\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b\u044c {RU_STATUS} \u0443\u0436\u0435 20 \u0434\u043d\u0435\u0439</p>"
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)
        self.assertEqual(report["changes"], [])

    def test_script_alias_preserved(self):
        html = f'<script>const legacy="{RU_STATUS}";</script>'
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_style_block_preserved(self):
        html = f'<style>.x::before{{content:"{RU_STATUS}";}}</style>'
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_comment_preserved(self):
        html = f"<!-- {RU_STATUS} -->"
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_data_ru_and_data_uk_both_corrected(self):
        html = f'<div data-ru="{RU_STATUS}" data-uk="{UK_STATUS}">{RU_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertIn(f'data-ru="{RU_STATUS_NEW}"', out)
        self.assertIn(f'data-uk="{UK_STATUS_NEW}"', out)
        self.assertIn(f">{RU_STATUS_NEW}<", out)

    def test_four_span_sequence_corrected(self):
        html = ('<div style="display:flex"><span>\u041a\u043e\u0440\u0435\u044f</span><span>\u041c\u043e\u0440\u0435</span>'
                '<span>\u0413\u0440\u0443\u0437\u0438\u044f</span><span>\u041a\u0438\u0435\u0432</span></div>')
        out, report = transform.transform_html(html)
        self.assertIn("<span>\u041f\u0430\u0440\u043e\u043c</span>", out)
        self.assertIn("<span>\u041a\u043e\u0440\u0435\u044f</span>", out)
        self.assertIn("<span>\u0413\u0440\u0443\u0437\u0438\u044f</span>", out)
        self.assertIn("<span>\u041a\u0438\u0435\u0432</span>", out)
        self.assertEqual(report["ambiguous"], [])

    def test_four_span_out_of_order_not_transformed(self):
        html = ('<div><span>\u041c\u043e\u0440\u0435</span><span>\u041a\u043e\u0440\u0435\u044f</span>'
                '<span>\u0413\u0440\u0443\u0437\u0438\u044f</span><span>\u041a\u0438\u0435\u0432</span></div>')
        out, report = transform.transform_html(html)
        self.assertIn("<span>\u041c\u043e\u0440\u0435</span>", out)
        self.assertEqual(len(report["ambiguous"]), 1)

    def test_four_children_not_spans_not_transformed(self):
        html = ('<div><i>\u041a\u043e\u0440\u0435\u044f</i><i>\u041c\u043e\u0440\u0435</i>'
                '<i>\u0413\u0440\u0443\u0437\u0438\u044f</i><i>\u041a\u0438\u0435\u0432</i></div>')
        out, report = transform.transform_html(html)
        self.assertIn(">\u041c\u043e\u0440\u0435<", out)

    def test_four_spans_different_words_untouched(self):
        html = '<div><span>A</span><span>B</span><span>C</span><span>D</span></div>'
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_standalone_more_ambiguous(self):
        html = "<div><span>\u041c\u043e\u0440\u0435</span></div>"
        out, report = transform.transform_html(html)
        self.assertIn("<span>\u041c\u043e\u0440\u0435</span>", out)
        self.assertEqual(len(report["ambiguous"]), 1)

    def test_chip_short_status(self):
        html = f'<div class="chip">{RU_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertIn(f">{RU_STATUS_NEW}<", out)

    def test_status_pill_short_status(self):
        html = f'<span class="status-pill">{RU_STATUS}</span>'
        out, report = transform.transform_html(html)
        self.assertIn(f">{RU_STATUS_NEW}<", out)

    def test_uk_status_short(self):
        html = f'<div class="chip">{UK_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertIn(f">{UK_STATUS_NEW}<", out)

    def test_etap_tut_krug_short_word(self):
        html = '<div class="etap tut"><span class="krug">\u041c\u043e\u0440\u0435</span></div>'
        out, report = transform.transform_html(html)
        self.assertIn(">\u041f\u0430\u0440\u043e\u043c<", out)

    def test_krug_without_etap_tut_ambiguous(self):
        html = '<div><span class="krug">\u041c\u043e\u0440\u0435</span></div>'
        out, report = transform.transform_html(html)
        self.assertIn(">\u041c\u043e\u0440\u0435<", out)
        self.assertEqual(len(report["ambiguous"]), 1)

    def test_long_pattern(self):
        html = f"<p>{RU_STATUS} \u00b7 \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f</p>"
        out, report = transform.transform_html(html)
        self.assertIn(f"{RU_STATUS_NEW} \u00b7 \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f", out)

    def test_heading_status(self):
        html = f"<h3>{RU_STATUS}: \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0441\u0435\u0433\u043e\u0434\u043d\u044f</h3>"
        out, report = transform.transform_html(html)
        self.assertIn(f"{RU_STATUS_NEW}: \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0441\u0435\u0433\u043e\u0434\u043d\u044f", out)

    def test_route_heading(self):
        html = "<h2>\u041c\u043e\u0440\u0435: \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f</h2>"
        out, report = transform.transform_html(html)
        self.assertIn("\u041f\u0430\u0440\u043e\u043c: \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f", out)

    def test_info_phrase(self):
        html = "<p>\u041c\u043e\u0440\u0435 \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f \u2014 \u043e\u043a\u043e\u043b\u043e 60 \u0434\u043d\u0435\u0439</p>"
        out, report = transform.transform_html(html)
        self.assertIn("\u041f\u0430\u0440\u043e\u043c \u041a\u043e\u0440\u0435\u044f \u2192 \u0413\u0440\u0443\u0437\u0438\u044f \u2014 \u043e\u043a\u043e\u043b\u043e 60 \u0434\u043d\u0435\u0439", out)

    def test_no_target_zero_changes(self):
        html = "<p>\u0417\u0434\u0435\u0441\u044c \u043d\u0435\u0442 \u0446\u0435\u043b\u0435\u0432\u043e\u0433\u043e \u0441\u043b\u043e\u0432\u0430.</p>"
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)
        self.assertEqual(report["changes"], [])

    def test_attribute_only_one_language_present(self):
        html = f'<div data-ru="{RU_STATUS}">{RU_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertIn(f'data-ru="{RU_STATUS_NEW}"', out)
        self.assertNotIn("data-uk", out)

    def test_non_target_attribute_untouched(self):
        html = f'<div data-ru="{RU_STATUS}" title="{RU_STATUS} \u0443\u0436\u0435 5 \u0434\u043d\u0435\u0439">{RU_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertIn(f'title="{RU_STATUS} \u0443\u0436\u0435 5 \u0434\u043d\u0435\u0439"', out)

    def test_void_element_untouched(self):
        html = f'<div class="chip">{RU_STATUS}<br>\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0435\u043d\u0438\u0435</div>'
        out, report = transform.transform_html(html)
        self.assertIn("<br>", out)

    def test_nested_chip_descendant(self):
        html = f'<div class="chip"><b>{RU_STATUS}</b></div>'
        out, report = transform.transform_html(html)
        self.assertIn(f">{RU_STATUS_NEW}<", out)

    def test_entity_preserved(self):
        html = "<p>\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f &amp; \u043f\u0430\u0440\u0442\u043d\u0451\u0440\u044b</p>"
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_multiple_independent_targets(self):
        html = (f'<div class="chip">{RU_STATUS}</div>'
                '<div><span>\u041c\u043e\u0440\u0435</span></div>')
        out, report = transform.transform_html(html)
        self.assertIn(f">{RU_STATUS_NEW}<", out)
        self.assertIn(">\u041c\u043e\u0440\u0435<", out)

    def test_report_change_count_status(self):
        html = f'<div class="chip">{RU_STATUS}</div>'
        out, report = transform.transform_html(html)
        self.assertEqual(len(report["changes"]), 1)

    def test_full_document_roundtrip_no_target(self):
        html = "<html><head><title>\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a</title></head><body><p>\u0422\u0435\u043a\u0441\u0442</p></body></html>"
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)

    def test_uk_short_word_context(self):
        html = '<div data-uk="\u041c\u043e\u0440\u0435">\u041c\u043e\u0440\u0435</div>'
        out, report = transform.transform_html(html)
        self.assertIn('data-uk="\u041f\u043e\u0440\u043e\u043c"', out)

    def test_uk_map_uses_real_source_phrase(self):
        # regression: previous defect used a fabricated "\u0412 \u043c\u043e\u0440\u0456" instead of real "\u0423 \u043c\u043e\u0440\u0456"
        html = f'<div class="chip">\u0412 \u043c\u043e\u0440\u0456</div>'
        out, report = transform.transform_html(html)
        self.assertEqual(out, html)


if __name__ == "__main__":
    unittest.main()
