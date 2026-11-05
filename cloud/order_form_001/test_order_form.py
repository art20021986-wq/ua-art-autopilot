"""Application view: exact edits of the live order page, strings and home link; the normal page keeps its blocks."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_home_link  # noqa: E402
import edit_order_page as page  # noqa: E402
from release_constants import HOME, PAGE, STRINGS  # noqa: E402

# Live sources read by LEAD-DESK-PROBE-20261105-R5 (home, order page) and R3 (strings); sanitized copies.
PROBES = HERE.parent / 'lead_desk_probe_001'
R5 = json.loads((PROBES / '20261105-R5.json').read_text())['files']
R3 = json.loads((PROBES / '20261105-R3.json').read_text())['files']


def live_home():
    """The home page as installed by HOME-STEP1-INSTALL-20261105 (step 1 edit on the R5 copy)."""
    spec = importlib.util.spec_from_file_location('installed_step1', HERE.parent / 'home_step1_001' / 'edit_home.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(R5[HOME]['source'].encode())


SOURCES = {HOME: live_home(), PAGE: R5[PAGE]['source'].encode(), STRINGS: R3[STRINGS]['source'].encode()}


class OrderFormTests(unittest.TestCase):
    def setUp(self):
        self.result = {name: value.decode() for name, value in candidate_builder.build(SOURCES, {}).items()}

    def test_strings_stay_valid_json_with_three_languages(self):
        data = json.loads(self.result[STRINGS])
        self.assertEqual({lang: data[lang]['application_title'] for lang in ('uk', 'ru', 'ka')},
                         {'uk': 'Оформлення заявки', 'ru': 'Оформление заявки', 'ka': 'განაცხადის გაფორმება'})
        before = json.loads(SOURCES[STRINGS])
        for lang in before:
            data[lang].pop('application_title')
        self.assertEqual(data, before)

    def test_page_heading_css_and_version(self):
        html = self.result[PAGE]
        self.assertEqual(html.count(page.CHECK_PAGE), 1)
        self.assertIn('order/order.js?v=20261105.1', html)
        self.assertNotIn('order/order.js?v=20261103.1', html)
        self.assertLess(html.index(page.CSS), html.index('</head>'))
        # The normal page keeps the model cards, «Обрати інше авто» and the SEO intro.
        for kept in ('id="model-section"', 'id="other-model"', 'id="ua-seo-order-intro"', 'id="order-form"'):
            self.assertEqual(html.count(kept), 1)
        self.assertLess(html.index('id="zayavka"'), html.index('id="countries"'))

    def test_css_only_acts_in_the_view(self):
        for rule in ('#zayavka{display:none}', '#zayavka:target{display:block}',
                     'body:has(#zayavka:target) #model-section', 'body:has(#zayavka:target) #ua-seo-order-intro'):
            self.assertIn(rule, page.CSS)

    def test_only_listed_fragments_change(self):
        html = self.result[PAGE]
        restored = html.replace(page.CSS, '', 1).replace('order/order.js?v=20261105.1', 'order/order.js?v=20261103.1', 1)
        restored = restored.replace('    <h2 id="zayavka" data-label="application_title">Оформлення заявки</h2>\n', '', 1)
        self.assertEqual(restored, SOURCES[PAGE].decode())
        home = self.result[HOME]
        self.assertEqual(home.replace(edit_home_link.NEW, edit_home_link.OLD, 1), SOURCES[HOME].decode())
        self.assertEqual(home.count(edit_home_link.CHECK), 1)

    def test_refuses_second_run(self):
        with self.assertRaises(ValueError):
            page.build(PAGE, self.result[PAGE].encode())
        with self.assertRaises(ValueError):
            edit_home_link.build(self.result[HOME].encode())

    def test_order_script_keeps_the_fragment(self):
        # setUrl() rebuilds the address from location.href, so #zayavka survives a country click.
        script = R3['video/order/order.js']['source']
        self.assertIn('const url=new URL(location.href);', script)
        self.assertIn("history[push?'pushState':'replaceState']({},'',url);", script)


if __name__ == '__main__':
    unittest.main()
