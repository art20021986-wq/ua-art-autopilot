#!/usr/bin/env python3
"""LEAD-SOURCE-001: the candidate on the live sources (pages and attribution.js fetched 2026-11-12, module fixtures of
the installed chain)."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_lead_source  # noqa: E402

F = HERE / 'fixtures'
PAGES = {'video/index.html': 'index.html', 'video/katalog.html': 'katalog.html', 'video/korea.html': 'korea.html'}


def source():
    value = {name: (F / fixture).read_bytes() for name, fixture in PAGES.items()}
    value['video/podbor.html'] = (F / 'podbor.html').read_bytes()  # already loads it: left out of the candidate
    value['video/order/attribution.js'] = (F / 'attribution.js.txt').read_bytes()
    value['site_ge_inject.py'] = (F / 'site_ge_inject.txt').read_bytes()
    value['ua_seo_landings.py'] = (F / 'ua_seo_landings.txt').read_bytes()
    value['catalog_design_golden.html'] = (F / 'katalog.html').read_bytes()
    return value


class Release(unittest.TestCase):
    def setUp(self):
        self.source = source()
        self.result = candidate_builder.build(self.source, {})

    def test_pages_load_the_script_once(self):
        for name in PAGES:
            before, after = self.source[name].decode(), self.result[name].decode()
            self.assertNotIn('order/attribution.js', before, name)
            self.assertEqual(after.count('order/attribution.js'), 1, name)
            self.assertEqual(after.replace(ua_lead_source.SCRIPT, '', 1), before, name)  # nothing else changes
            self.assertLess(after.index(ua_lead_source.SCRIPT), after.lower().index('</head>'), name)
            self.assertEqual(ua_lead_source.apply(after), after)
        self.assertIn('catalog_design_golden.html', self.result)

    def test_page_with_the_script_left_out(self):
        self.assertNotIn('video/podbor.html', self.result)

    def test_script_replaced(self):
        self.assertEqual(self.result['video/order/attribution.js'].decode(), ua_lead_source.JS)
        with self.assertRaisesRegex(ValueError, 'LEAD_SOURCE_SCRIPT_UNEXPECTED'):
            candidate_builder.build({**self.source, 'video/order/attribution.js': b'other'}, {})

    def test_new_script_keeps_the_contract(self):
        js = ua_lead_source.JS
        for text in ("var KEY = 'ua_attribution'", 'window.uaAttribution = function', "'gclid', 'gbraid', 'wbraid'",
                     "'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'", 'document.referrer'):
            self.assertIn(text, js)

    def test_landing_page(self):
        page = (F / 'landing_uk.html').read_text(encoding='utf-8')
        after = ua_lead_source.apply(page)
        self.assertEqual(after.replace(ua_lead_source.SCRIPT, '', 1), page)
        self.assertEqual(ua_lead_source.apply('<p>no head</p>'), '<p>no head</p>')

    def test_tails_and_refusal(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.rstrip().endswith('return ua_lead_source.apply(_ua_lead_source_base_inject(source))'))
        landings = self.result['ua_seo_landings.py'].decode()
        self.assertIn('_ua_lead_source_base_pages = pages', landings)
        for name in ('site_ge_inject.py', 'ua_seo_landings.py'):
            compile(self.result[name], name, 'exec')
            with self.assertRaisesRegex(ValueError, 'LEAD_SOURCE_ALREADY_APPLIED'):
                candidate_builder.edit(name, self.result[name])

    def load(self, folder, name, base):
        """The appended tail run on top of a stand-in base definition, imported as a module."""
        code = self.result[name].decode()
        path = Path(folder) / ('chain_' + name)
        path.write_text(base + code[code.index('# LEAD-SOURCE-001'):], encoding='utf-8')
        spec = importlib.util.spec_from_file_location('chain_' + name[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_chains_run(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'ua_lead_source.py').write_bytes(self.result['ua_lead_source.py'])
            sys.path.insert(0, folder)
            try:
                inject = self.load(folder, 'site_ge_inject.py',
                                   'def inject_html(source):\n    return source + \'<head></head>\'\n')
                self.assertEqual(inject.inject_html('<p>'), '<p><head>' + ua_lead_source.SCRIPT + '</head>')
                landings = self.load(folder, 'ua_seo_landings.py',
                                     'def pages(*a, **k):\n    return {"seo/ua/x.html": "<head></head><h1>x</h1>"}\n')
                self.assertEqual(landings.pages([], set(), set()),
                                 {'seo/ua/x.html': '<head>' + ua_lead_source.SCRIPT + '</head><h1>x</h1>'})
            finally:
                sys.path.remove(folder)


if __name__ == '__main__':
    unittest.main()
