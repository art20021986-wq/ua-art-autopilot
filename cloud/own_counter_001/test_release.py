#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs, the patches on the real sources and the pages."""
import datetime
import hashlib
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest

import candidate_builder
import ua_own_counter

HERE = Path(__file__).resolve().parent
FIXTURES = HERE/'fixtures'
# ua_seo_metadata.py is not in the repository; a stand-in with its two hook lines.
METADATA = b'import re\nimport ua_google_tag\n\n\ndef normalize(source):\n    return ua_google_tag.apply(source)\n'


def real(name):
    return (FIXTURES/name.replace('.py', '.txt')).read_bytes()


def installed():
    return {'ua_seo_metadata.py': METADATA, 'ua_seo_index.py': real('ua_seo_index.py'),
            'analitika_yadro.py': real('analitika_yadro.py'), 'analitika_otchet.py': real('analitika_otchet.py')}


def build(source, pages):
    pins = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
    original = candidate_builder.SOURCE_SHA256
    candidate_builder.SOURCE_SHA256 = pins
    try:
        return candidate_builder.build(source, pages)
    finally:
        candidate_builder.SOURCE_SHA256 = original


def module(source, name):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)/(name + '.py')
        path.write_bytes(source)
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value


class ReleaseTests(unittest.TestCase):
    def test_fixtures_are_the_installed_sources(self):
        for name in ('ua_seo_index.py', 'analitika_yadro.py', 'analitika_otchet.py'):
            self.assertEqual(hashlib.sha256(real(name)).hexdigest(), candidate_builder.SOURCE_SHA256[name])

    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH:ua_seo_metadata.py'):
            candidate_builder.build(installed(), {})

    def test_planned_files_and_pages(self):
        counted = '<html><body>x' + ua_own_counter.LINE + '</body></html>'
        pages = {'video/UA-0018.html': b'<html><head></head><body>card</body></html>', 'video/seo/ua/a.html': counted.encode()}
        result = build(installed(), pages)
        self.assertEqual(sorted(result), ['analitika_otchet.py', 'analitika_yadro.py', 'ua_own_counter.py',
                                          'ua_seo_index.py', 'ua_seo_metadata.py', 'video/UA-0018.html'])
        for name, value in result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        self.assertEqual(result['video/UA-0018.html'].count(b'UA-ANALIT-V1'), 1)

    def test_patch_needs_its_anchors_and_runs_once(self):
        with self.assertRaisesRegex(ValueError, 'PATCH_ANCHOR:ua_seo_metadata.py'):
            build({**installed(), 'ua_seo_metadata.py': b'import ua_google_tag\n'}, {})
        patched = build(installed(), {})
        with self.assertRaisesRegex(ValueError, 'ALREADY_PATCHED'):
            build({**installed(), 'analitika_yadro.py': patched['analitika_yadro.py']}, {})

    def test_writers_add_both_counters(self):
        patched = build(installed(), {})
        sys.modules['ua_own_counter'] = ua_own_counter
        sys.modules['ua_google_tag'] = types.SimpleNamespace(apply=lambda html: html.replace('<head>', '<head>G'))
        try:
            meta = module(patched['ua_seo_metadata.py'], 'meta_under_test')
        finally:
            del sys.modules['ua_google_tag']
        self.assertEqual(meta.normalize('<html><head></head><body></body></html>'),
                         '<html><head>G</head><body>' + ua_own_counter.LINE + '</body></html>')
        self.assertIn(b"ua_own_counter.apply(ua_google_tag.apply(html)).encode('utf-8')", patched['ua_seo_index.py'])

    def test_script_keeps_the_original_source_on_inner_pages(self):
        script = module(build(installed(), {})['analitika_yadro.py'], 'yadro_under_test').SKRIPT
        line = [x for x in script.splitlines() if 'location.hostname' in x and 'indexOf' in x]
        self.assertEqual(line, ["  if(h.indexOf(location.hostname.replace(/^www\\./,''))>=0) return ''; // UA-OWN-COUNTER-001"])

    def test_report_days_start_at_kyiv_midnight_and_site_is_no_source(self):
        report = module(build(installed(), {})['analitika_otchet.py'], 'otchet_under_test')
        for period in ('today', 'yesterday', '7d', '30d'):
            start, _ = report.granicy(period)
            local = datetime.datetime.fromtimestamp(start, report._kiev())
            self.assertEqual((local.hour, local.minute), (0, 0), period)
        self.assertEqual(report.klass_istochnika('uaart.com.ua', None, None), 'Прямая ссылка')
        self.assertNotEqual(report.klass_istochnika('Google', None, None), 'Прямая ссылка')

    def test_counter_once_before_body_end(self):
        page = '<html><body><p>x</p></BODY></html>'
        counted = ua_own_counter.apply(page)
        self.assertEqual(counted, '<html><body><p>x</p>' + ua_own_counter.LINE + '</BODY></html>')
        self.assertEqual(ua_own_counter.apply(counted), counted)
        self.assertEqual(ua_own_counter.apply('<html>no body end</html>'), '<html>no body end</html>')
        self.assertIn("/ua/a.js?v=1", ua_own_counter.LINE)

    def test_page_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ('video/UA-0018.html', 'video/UA-0018-diag.html', 'video/UA-0001-00cf71c0.html',
                             'video/ru/UA-0018.html', 'site/UA-0018-diag.html', 'video/seo/gu/x.html',
                             'video/preview/UA-0001.html', 'video/index.html', 'video/privacy.html'):
                (root/relative).parent.mkdir(parents=True, exist_ok=True)
                (root/relative).write_text('x')
            self.assertEqual(sorted(candidate_builder.page_paths(root)),
                             ['site/UA-0018-diag.html', 'video/UA-0001-00cf71c0.html', 'video/UA-0018-diag.html',
                              'video/UA-0018.html', 'video/ru/UA-0018.html', 'video/seo/gu/x.html'])


if __name__ == '__main__':
    unittest.main()
