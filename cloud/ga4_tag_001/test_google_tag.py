#!/usr/bin/env python3
"""The tag module and the writer hooks that keep it on later page writes."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import candidate_builder
import ua_google_tag as tag

HERE = Path(__file__).resolve().parent


class TagTests(unittest.TestCase):
    def test_inserted_right_after_head_once(self):
        page = '<!doctype html><html><HEAD lang="uk"><title>t</title></head><body><header>x</header></body></html>'
        tagged = tag.apply(page)
        self.assertTrue(tagged.startswith('<!doctype html><html><HEAD lang="uk">' + tag.SNIPPET + '<title>'))
        self.assertEqual(tag.apply(tagged), tagged)

    def test_pages_without_head_are_unchanged(self):
        for page in ('', '<html><header>no head</header></html>', None):
            self.assertEqual(tag.apply(page), page)

    def test_snippet_loads_the_property_and_reports_leads(self):
        self.assertIn('googletagmanager.com/gtag/js?id=G-6SRBQK6GY4', tag.SNIPPET)
        self.assertIn("gtag('config','G-6SRBQK6GY4')", tag.SNIPPET)
        for text in ("'generate_lead','order_form'", "'generate_lead','order_telegram'", "lead('contact',m)",
                     "'phone'", "'viber'", "'telegram'", "'whatsapp'"):
            self.assertIn(text, tag.SNIPPET)
        self.assertNotIn('</script', tag.EVENTS)


class PageSelectionTests(unittest.TestCase):
    def test_core_cards_and_landings_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('video/index.html', 'video/UA-0018.html', 'video/UA-0018-diag.html',
                         'video/UA-0018-bfcd1711.html', 'video/google609494476a22f741.html', 'site/katalog.html',
                         'video/seo/ua/a.html', 'video/seo/gu/b.html', 'video/preview/index.html'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('<html><head></head></html>')
            self.assertEqual(candidate_builder.page_paths(root), [
                'video/UA-0018.html', 'video/index.html', 'site/katalog.html', 'video/seo/ua/a.html',
                'video/seo/gu/b.html'])


class WriterHookTests(unittest.TestCase):
    def test_landing_writer_adds_the_tag(self):
        written = {}
        stubs = {
            'ua_google_sitemap': types.SimpleNamespace(submit=lambda: {}),
            'ua_indexnow': types.SimpleNamespace(submit=lambda urls: {}),
            'ua_seo_catalog': types.SimpleNamespace(cars=lambda text: []),
            'ua_seo_landings': types.SimpleNamespace(
                MODEL_META='ua-model', LANGS=(), DIRS={},
                pages=lambda cars, kept, existing: {'seo/ua/x.html': '<html><head></head></html>'}),
            'ua_seo_sitemap': types.SimpleNamespace(
                LANDINGS='seo/*/*.html', sitemap=lambda root: b'',
                write=lambda path, data: written.setdefault(path.name, data) is data),
        }
        with patch.dict(sys.modules, stubs), tempfile.TemporaryDirectory() as temp:
            sys.modules.pop('ua_seo_index', None)
            sys.path.insert(0, str(HERE))
            try:
                import ua_seo_index
                (Path(temp) / 'katalog.html').write_text('')
                ua_seo_index.refresh(temp)
            finally:
                sys.path.remove(str(HERE))
                sys.modules.pop('ua_seo_index', None)
        self.assertIn(b'G-6SRBQK6GY4', written['x.html'])

    def test_core_page_normalize_adds_the_tag_once(self):
        # The installed SEO modules this one imports, as last released.
        folders = [str(HERE)] + [str(HERE.parent / f) for f in ('seo_landings_002', 'seo_models_001', 'ai_search_001',
                                                               'seo_growth_001')]
        names = ('ua_seo_metadata', 'ua_seo_landings', 'ua_seo_order_models', 'ua_seo_schema', 'ua_seo_catalog')
        home = json.loads((HERE.parent / 'home_layout_001/live_home.json').read_text())['files']
        page = base64.b64decode(home['https://www.uaart.com.ua/video/index.html']['b64']).decode()
        saved = {name: sys.modules.pop(name) for name in names if name in sys.modules}
        sys.path[:0] = folders
        try:
            import ua_seo_metadata
            once = ua_seo_metadata.normalize(page, 'index.html')
            self.assertEqual(once.count(tag.MARK), 1)
            self.assertEqual(ua_seo_metadata.normalize(once, 'index.html'), once)
        finally:
            del sys.path[:len(folders)]
            for name in names:
                sys.modules.pop(name, None)
            sys.modules.update(saved)


if __name__ == '__main__':
    unittest.main()
