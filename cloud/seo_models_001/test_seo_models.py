#!/usr/bin/env python3
"""Custom-order pages: Tucson, Sportage, Santa Fe and Japan; links to them; unchanged pages stay unchanged."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

# Unchanged installed modules come from the previous releases.
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'gsc_growth_001'), str(HERE.parent / 'ai_search_001'),
                str(HERE.parent / 'seo_growth_001')]

import ua_seo_landings as landings  # noqa: E402
import ua_seo_index  # noqa: E402
import ua_seo_order_models as order_models  # noqa: E402

CARS = [{'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'mileage_km': 50000,
         'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None},
        {'key': ('Hyundai', 'Sonata'), 'name': 'Hyundai Sonata 2018', 'code': 'UA-0011', 'price_usd': 11400,
         'mileage_km': 163400, 'stage': 3, 'url': 'https://www.uaart.com.ua/video/UA-0011.html', 'image': None}]
MODELS = {('Hyundai', 'Tucson'): ('seo/ua/hyundai-tucson-koreya-kyiv.html', 'seo/ru/hyundai-tucson-koreya-kiev.html'),
          ('Kia', 'Sportage'): ('seo/ua/kia-sportage-koreya-kyiv.html', 'seo/ru/kia-sportage-koreya-kiev.html'),
          ('Hyundai', 'Santa Fe'): ('seo/ua/hyundai-santa-fe-koreya-kyiv.html', 'seo/ru/hyundai-santa-fe-koreya-kiev.html')}
JAPAN = {'uk': 'seo/ua/avto-z-yaponii-pid-zamovlennia.html', 'ru': 'seo/ru/avto-iz-yaponii-pod-zakaz.html'}


def graph(html):
    return json.loads(re.search(r'id="ua-seo-ld">(.*?)</script>', html).group(1))['@graph']


def faq(html):
    return [n for n in graph(html) if n['@type'] == 'FAQPage'][0]['mainEntity']


class ModelPageTests(unittest.TestCase):
    def test_korean_order_models_in_both_languages(self):
        pages = landings.pages(CARS)
        for key, paths in MODELS.items():
            for lang, relative in zip(landings.LANGS, paths):
                html, texts = pages[relative], order_models.KOREA[key][lang]
                self.assertEqual(landings.path(lang, key), relative)
                self.assertIn('<meta name="ua-seo-model" content="%s">' % '|'.join(key), html)
                self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/%s">' % relative, html)
                self.assertIn('<meta name="description" content="%s">' % texts['desc'], html)
                for text in (texts['about'],) + texts['versions']:
                    self.assertIn(text, html)
                self.assertEqual([q['name'] for q in faq(html)], [q for q, _ in texts['faq']])
                self.assertIn(landings.T[lang]['cta'], html)
                self.assertNotIn(' $', html.split('<h1>')[1].split('</h1>')[0])  # no invented price

    def test_texts_differ_between_models(self):
        for lang in landings.LANGS:
            about = [order_models.KOREA[key][lang]['about'] for key in MODELS]
            self.assertEqual(len(set(about)), len(about))

    def test_linked_from_hub_and_other_model_pages(self):
        pages = landings.pages(CARS)
        for lang in landings.LANGS:
            for key in MODELS:
                link = '/video/' + landings.path(lang, key)
                self.assertIn(link, pages[landings.path(lang)])
                self.assertIn(link, pages[landings.path(lang, ('Kia', 'K5'))])

    def test_page_with_cars_keeps_catalog_prices(self):
        car = dict(CARS[0], key=('Kia', 'Sportage'), name='Kia Sportage 2022', price_usd=21500)
        html = landings.pages([car])[MODELS[('Kia', 'Sportage')][0]]
        self.assertIn('21\xa0500 $', html)
        self.assertIn(order_models.KOREA[('Kia', 'Sportage')]['uk']['about'], html)

    def test_order_models_are_kept_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative, html in landings.pages(CARS).items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text(html, encoding='utf-8')
            self.assertEqual(ua_seo_index.kept_keys(root), {('Kia', 'K5'), ('Hyundai', 'Sonata')} | set(MODELS))


class JapanPageTests(unittest.TestCase):
    def test_japan_page_in_both_languages(self):
        pages = landings.pages(CARS, existing={'seo/gu/avtomobili-koreidan-sakartveloshi.html'})
        for lang, relative in JAPAN.items():
            html, j = pages[relative], order_models.JAPAN[lang]
            self.assertEqual(landings.path(lang, landings.JAPAN), relative)
            self.assertIn('<h1>%s</h1>' % j['h1'], html)
            self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/%s">' % relative, html)
            self.assertIn('href="/video/podbor.html?strana=japan&amp;lang=%s"' % lang, html)
            self.assertNotIn('ua-seo-model', html)
            self.assertNotIn('hreflang="ka"', html)
            self.assertNotIn('Корея → Грузія', html)
            self.assertNotIn('Корея → Грузия', html)
            for name, _ in j['models']:
                self.assertIn('<h3>%s</h3>' % name, html)
            self.assertEqual(len(faq(html)), len(j['faq']))
            breadcrumbs = [n for n in graph(html) if n['@type'] == 'BreadcrumbList'][0]['itemListElement']
            self.assertEqual(breadcrumbs[-1]['item'], 'https://www.uaart.com.ua/video/' + relative)
            # linked from the order page, and back
            self.assertIn('/video/' + relative, pages[landings.path(lang, landings.ORDER)])
            self.assertIn('/video/' + landings.path(lang, landings.ORDER), html)

    def test_japan_page_is_never_a_kept_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative, html in landings.pages([]).items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text(html, encoding='utf-8')
            self.assertEqual(ua_seo_index.kept_keys(root), set(MODELS))


class UnchangedTests(unittest.TestCase):
    """Pages of the previous release change only by the new links."""

    def strip(self, html):
        html = re.sub(r'<li><a href="/video/seo/[a-z]+/(hyundai-tucson|kia-sportage|hyundai-santa-fe)-[^"]+">[^<]*</a></li>', '', html)
        return re.sub(r'<p><a href="/video/seo/[a-z]+/avto-[a-z]+-yaponii-[^"]+">[^<]*</a></p>', '', html)

    def test_previous_pages(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('previous_landings', HERE.parent / 'gsc_growth_001' / 'ua_seo_landings.py')
        previous = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(previous)
        old, new = previous.pages(CARS), landings.pages(CARS)
        for relative, html in old.items():
            self.assertEqual(self.strip(new[relative]), html, relative)


if __name__ == '__main__':
    unittest.main()
