#!/usr/bin/env python3
"""Google sitemap submission, its call from refresh, and the order page."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

# Unchanged installed modules come from the previous releases.
HERE = Path(__file__).resolve().parent
sys.path += [str(HERE.parent / 'ai_search_001'), str(HERE.parent / 'seo_growth_001')]

import ua_google_sitemap as google  # noqa: E402
import ua_indexnow  # noqa: E402
import ua_seo_index  # noqa: E402
import ua_seo_landings as landings  # noqa: E402

CAR = {'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'year': 2021,
       'mileage_km': 50000, 'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None}


class Response(io.BytesIO):
    status = 204


class GoogleSitemapTests(unittest.TestCase):
    def key(self, temp):
        path = Path(temp) / 'uaart-autopilot-110fb4d36d23.txt'
        path.write_text('{}')
        return (Path(temp) / 'absent.json', path)

    def test_put_with_bearer_and_empty_body(self):
        seen = []
        def opener(request, timeout):
            seen.append((request.get_method(), request.full_url, request.headers, request.data, timeout))
            return Response()
        with tempfile.TemporaryDirectory() as temp:
            result = google.submit(self.key(temp), token=lambda key: 'tkn', opener=opener)
        self.assertEqual(result, {'status': 'PASS', 'http': 204})
        method, url, headers, data, timeout = seen[0]
        self.assertEqual((method, data, timeout, headers['Authorization']), ('PUT', b'', 10, 'Bearer tkn'))
        self.assertEqual(url, 'https://www.googleapis.com/webmasters/v3/sites/https%3A%2F%2Fwww.uaart.com.ua%2F'
                              '/sitemaps/https%3A%2F%2Fwww.uaart.com.ua%2Fsitemap.xml')

    def test_failures_are_reported_not_raised(self):
        def refused(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'Forbidden', {}, None)
        def no_library(key):
            raise ImportError('google')
        with tempfile.TemporaryDirectory() as temp:
            self.assertIn('403', google.submit(self.key(temp), token=lambda k: 't', opener=refused)['error'])
            self.assertEqual(google.submit(self.key(temp), token=no_library)['status'], 'FAIL')
        self.assertEqual(google.submit((Path('/nonexistent/key'),)), {'status': 'SKIP', 'reason': 'KEY_MISSING'})


class RefreshTests(unittest.TestCase):
    def test_google_asked_only_when_sitemap_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'katalog.html').write_text('<html></html>', encoding='utf-8')
            (root / 'index.html').write_text('x', encoding='utf-8')
            calls = []
            with patch.object(ua_seo_index.ua_seo_catalog, 'cars', return_value=[]), \
                 patch.object(ua_indexnow, 'submit', return_value={'status': 'PASS'}), \
                 patch.object(google, 'submit', side_effect=lambda: calls.append(1) or {'status': 'PASS', 'http': 204}):
                first = ua_seo_index.refresh(root)
                again = ua_seo_index.refresh(root)
            self.assertTrue((root / 'seo/ua/avto-pid-zamovlennia-kyiv.html').is_file())
        self.assertEqual((first['google'], again['google'], len(calls)), ({'status': 'PASS', 'http': 204}, {'status': 'SKIP'}, 1))


class OrderPageTests(unittest.TestCase):
    def test_order_pages_in_both_languages(self):
        pages = landings.pages([CAR], existing={'seo/gu/avtomobili-koreidan-sakartveloshi.html'})
        for lang, slug, h1 in (('uk', 'seo/ua/avto-pid-zamovlennia-kyiv.html', 'Авто під замовлення в Києві'),
                               ('ru', 'seo/ru/avto-pod-zakaz-kiev.html', 'Авто под заказ в Киеве')):
            html = pages[slug]
            self.assertIn('<h1>%s</h1>' % h1, html)
            self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/%s">' % slug, html)
            self.assertNotIn('ua-seo-model', html)
            self.assertNotIn('hreflang="ka"', html)
            self.assertEqual(html.count('podbor.html?strana='), 5)
            graph = json.loads(re.search(r'id="ua-seo-ld">(.*?)</script>', html).group(1))['@graph']
            faq = [n for n in graph if n['@type'] == 'FAQPage'][0]['mainEntity']
            self.assertEqual(len(faq), 5)
            self.assertEqual(html.count('<h3>'), 5)
            self.assertIn(slug, pages[landings.path(lang)])

    def test_order_page_is_never_a_kept_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative, html in landings.pages([CAR]).items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text(html, encoding='utf-8')
            self.assertEqual(ua_seo_index.kept_keys(root), {('Kia', 'K5')})

    def test_order_page_without_cars(self):
        html = landings.pages([])['seo/ru/avto-pod-zakaz-kiev.html']
        self.assertNotIn('Примеры', html)
        self.assertIn('Частые вопросы', html)


if __name__ == '__main__':
    unittest.main()
