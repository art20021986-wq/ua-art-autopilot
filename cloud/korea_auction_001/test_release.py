"""The JPAUTO-KOREA-001 candidate built from copies of the live files (home page, dialog script, selection strings;
site_ge_inject and the order hand-offs as recorded by earlier releases)."""
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_home  # noqa: E402

FIX = HERE / 'fixtures'
CONTRACT = (b"def normalize(data, catalog, consent_version):\n"
            b"    if isinstance(data, dict) and data.get('schema_version') == 'ua_order_request.quick.v1':\n"
            b"        from .quick import normalize as normalize_quick\n"
            b"        return normalize_quick(data, catalog, consent_version)\n")
CRM = (b"def label(data, catalog):\n"
       b"    if True:\n"
       b"        if data.get('schema_version') == 'ua_order_request.card.v1':\n"
       b"            from .card_lead import label as card_label\n"
       b"            country = card_label(data)\n"
       b"        else:\n"
       b"            country = preference_summary.country_label(data, catalog)\n"
       b"    return country\n\n\n"
       b"def detail_view(row, catalog):\n"
       b"    data = row['data']\n"
       b"    if data.get('schema_version') == 'ua_order_request.quick.v1':\n"
       b"        from .quick import detail as quick_detail\n"
       b"        return quick_detail(row, catalog)\n")


def live_source():
    return {'site_ge_inject.py': (FIX / 'site_ge_inject_sample.txt').read_bytes(),
            'video/index.html': (FIX / 'index_live.html').read_bytes(),
            'video/order/quick-lead.js': (FIX / 'quick-lead_live.js').read_bytes(),
            'video/order/order-strings.json': (FIX / 'order-strings_live.json').read_bytes(),
            'ua_order/contract.py': CONTRACT, 'ua_order/crm.py': CRM}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.source = live_source()
        self.result = candidate_builder.build(self.source, {})

    def test_files(self):
        self.assertEqual(sorted(self.result), sorted(set(candidate_builder.SOURCE_FILES) | {
            'video/korea.html', 'ua_korea_home.py', 'ua_order/auction.py'}))
        self.assertEqual(set(candidate_builder.SOURCE_FILES), set(self.source))

    def test_python_compiles(self):
        for name, value in self.result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')

    def test_inject_hook_appended_once(self):
        text = self.result['site_ge_inject.py'].decode()
        self.assertTrue(text.startswith(self.source['site_ge_inject.py'].decode().rstrip('\n')))
        self.assertEqual(text.count('ua_korea_home.apply('), 1)
        with self.assertRaises(ValueError):
            candidate_builder.inject(self.result['site_ge_inject.py'])

    def test_home_only_additions(self):
        home = self.result['video/index.html'].decode()
        self.assertEqual(ua_korea_home.remove(home), self.source['video/index.html'].decode())
        self.assertEqual(home.count(ua_korea_home.MARK), 1)

    def test_korea_page(self):
        page = self.result['video/korea.html'].decode()
        self.assertIn('id="quick-lead-dialog"', page)
        self.assertIn('/video/order/quick-lead.js', page)
        self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/korea.html">', page)

    def test_order_files(self):
        self.assertIn(b"'ua_order_request.auction.v1'", self.result['video/order/quick-lead.js'])
        strings = json.loads(self.result['video/order/order-strings.json'])
        self.assertEqual(strings['uk']['title'], 'Індивідуальне замовлення автомобіля')
        self.assertIn(b'from .auction import normalize', self.result['ua_order/contract.py'])
        self.assertIn(b'from .auction import label', self.result['ua_order/crm.py'])
        self.assertIn(b'from .auction import detail', self.result['ua_order/crm.py'])

    def test_second_build_refused(self):
        again = dict(self.source, **{k: v for k, v in self.result.items() if k in self.source})
        with self.assertRaises(ValueError):
            candidate_builder.build(again, {})

    def test_only_the_home_page_is_a_page(self):
        self.assertTrue(candidate_builder.is_page('video/index.html'))
        self.assertFalse(candidate_builder.is_page('video/korea.html'))


if __name__ == '__main__':
    unittest.main()
