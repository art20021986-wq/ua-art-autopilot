#!/usr/bin/env python3
"""IndexNow submission, sitemap diff and hub FAQ."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

# Unchanged installed modules (ua_seo_catalog, ua_seo_sitemap) come from the previous release.
sys.path.append(str(Path(__file__).resolve().parent.parent / 'seo_growth_001'))
import ua_indexnow
import ua_seo_index
import ua_seo_landings

CAR = {'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'year': 2021,
       'mileage_km': 50000, 'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None}


class Response(io.BytesIO):
    status = 202


class IndexNowTests(unittest.TestCase):
    def test_submits_only_own_video_urls(self):
        seen = []
        def opener(request, timeout):
            seen.append((request.full_url, json.loads(request.data), timeout))
            return Response()
        result = ua_indexnow.submit(['https://www.uaart.com.ua/video/UA-0018.html', 'https://example.com/x',
                                     'https://www.uaart.com.ua/sitemap.xml'], opener=opener)
        self.assertEqual(result, {'status': 'PASS', 'http': 202, 'urls': 1})
        url, body, timeout = seen[0]
        self.assertEqual(url, ua_indexnow.ENDPOINT)
        self.assertEqual(body, {'host': 'www.uaart.com.ua', 'key': ua_indexnow.KEY,
                                'keyLocation': 'https://www.uaart.com.ua/video/%s.txt' % ua_indexnow.KEY,
                                'urlList': ['https://www.uaart.com.ua/video/UA-0018.html']})
        self.assertEqual(timeout, 5)

    def test_failure_is_reported_not_raised(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'Forbidden', {}, None)
        result = ua_indexnow.submit(['https://www.uaart.com.ua/video/x.html'], opener=opener)
        self.assertEqual((result['status'], result['urls']), ('FAIL', 1))
        self.assertIn('403', result['error'])

    def test_nothing_to_send(self):
        self.assertEqual(ua_indexnow.submit([], opener=None), {'status': 'SKIP'})


class RefreshTests(unittest.TestCase):
    def test_changed_sitemap_entries_are_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'katalog.html').write_text('<html></html>', encoding='utf-8')
            for name in ('index.html', 'old.html'):
                (root / name).write_text('x', encoding='utf-8')
            (root / 'sitemap.xml').write_text(
                '<url><loc>https://www.uaart.com.ua/video/index.html</loc><lastmod>2020-01-01</lastmod></url>\n'
                '<url><loc>https://www.uaart.com.ua/video/UA-0001.html</loc><lastmod>2020-01-01</lastmod></url>\n',
                encoding='utf-8')
            sent = []
            with patch.object(ua_seo_index.ua_seo_catalog, 'cars', return_value=[]), \
                 patch.object(ua_indexnow, 'submit', side_effect=lambda urls: sent.append(set(urls)) or {'status': 'PASS'}):
                result = ua_seo_index.refresh(root)
                self.assertEqual(result['indexnow'], {'status': 'PASS'})
                again = ua_seo_index.refresh(root)
        hubs = {'https://www.uaart.com.ua/video/' + ua_seo_landings.path(lang) for lang in ua_seo_landings.LANGS}
        self.assertEqual(sent[0], {'https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html',
                                   'https://www.uaart.com.ua/video/UA-0001.html'} | hubs)
        self.assertEqual((len(sent), again['indexnow']), (1, {'status': 'SKIP'}))


class FaqTests(unittest.TestCase):
    def test_hub_answers_in_text_and_schema(self):
        pages = ua_seo_landings.pages([CAR])
        for lang, title in (('uk', 'Часті питання'), ('ru', 'Частые вопросы')):
            html = pages[ua_seo_landings.path(lang)]
            self.assertIn('<h2>%s</h2>' % title, html)
            self.assertEqual(html.count('<h3>'), 6)
            graph = json.loads(re.search(r'id="ua-seo-ld">(.*?)</script>', html).group(1))['@graph']
            faq = [n for n in graph if n['@type'] == 'FAQPage'][0]['mainEntity']
            self.assertEqual(len(faq), 6)
            self.assertIn('19\xa0300', faq[0]['acceptedAnswer']['text'])
            self.assertIn(faq[0]['name'], html)
        model = pages[ua_seo_landings.path('uk', ('Kia', 'K5'))]
        self.assertNotIn('FAQPage', model)

    def test_no_price_answer_without_cars(self):
        html = ua_seo_landings.pages([])[ua_seo_landings.path('ru')]
        self.assertEqual(html.count('<h3>'), 5)
        self.assertNotIn('Сколько стоит', html)


if __name__ == '__main__':
    unittest.main()
