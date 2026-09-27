import json
from pathlib import Path
import unittest

from build import one_span, patch_home, patch_form, CONFIG


class BuildTest(unittest.TestCase):
    def test_nested_element_span_preserves_surrounding_bytes(self):
        source='<html>\n<main><div id="target">A<div>B</div>C</div><p>Keep</p></main></html>'
        a,b=one_span(source,lambda tag,attrs:attrs.get('id')=='target')
        self.assertEqual(source[a:b],'<div id="target">A<div>B</div>C</div>')

    def test_home_country_links_do_not_change_inventory_count_or_stage(self):
        source='<html><head></head><body><p id="count">23</p><div class="countries-inline"><span>Five countries</span></div><p>В Грузии</p></body></html>'
        result=patch_home(source,json.loads(CONFIG.read_text()))
        self.assertIn('<p id="count">23</p>',result)
        self.assertIn('<p>В Грузии</p>',result)
        self.assertEqual(result.count('data-order-country="'),8)
        self.assertIn('strana=georgia&amp;lang=uk',result)

    def test_unknown_form_structure_fails_closed(self):
        with self.assertRaises(ValueError):patch_form('<html><body>New unknown form</body></html>')


if __name__=='__main__':unittest.main()
