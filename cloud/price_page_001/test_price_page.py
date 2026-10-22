#!/usr/bin/env python3
"""The price page: real catalog prices by model and budget, FAQ, links from the hubs."""
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


def car(code, name, key, price, year):
    return {'key': key, 'name': '%s %d' % (name, year), 'code': code, 'price_usd': price, 'mileage_km': 100000,
            'stage': 4, 'url': 'https://www.uaart.com.ua/video/%s.html' % code, 'image': None}


CARS = [car('UA-0007', 'Mercedes-Benz B-Class', ('Mercedes-Benz', 'B-Class'), 8200, 2011),
        car('UA-0018', 'Kia K5', ('Kia', 'K5'), 19300, 2023),
        car('UA-0010', 'Kia K5', ('Kia', 'K5'), 11700, 2018),
        car('UA-0017', 'Audi A6', ('Audi', 'A6'), 21000, 2015),
        car('UA-0015', 'Hyundai Sonata', ('Hyundai', 'Sonata'), None, 2018)]
SLUGS = {'uk': 'seo/ua/skilky-koshtuie-avto-z-korei-pid-kliuch.html', 'ru': 'seo/ru/skolko-stoit-avto-iz-korei-pod-kluch.html'}


class PricePageTests(unittest.TestCase):
    def test_price_page_in_both_languages(self):
        pages = landings.pages(CARS, existing={'seo/gu/avtomobili-koreidan-sakartveloshi.html'})
        for lang, h1 in (('uk', 'Скільки коштує авто з Кореї під ключ'), ('ru', 'Сколько стоит авто из Кореи под ключ')):
            html = pages[SLUGS[lang]]
            self.assertEqual(landings.path(lang, landings.PRICE), SLUGS[lang])
            self.assertIn('<h1>%s</h1>' % h1, html)
            self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/%s">' % SLUGS[lang], html)
            self.assertNotIn('ua-seo-model', html)
            self.assertNotIn('hreflang="ka"', html)
            self.assertIn('8\xa0200 $', html)
            self.assertIn('<td>21\xa0000 $</td>', html)
            self.assertIn('11\xa0700–19\xa0300 $', html)  # Kia K5 row
            self.assertIn('2018–2023', html)
            graph = json.loads(re.search(r'id="ua-seo-ld">(.*?)</script>', html).group(1))['@graph']
            faq = [n for n in graph if n['@type'] == 'FAQPage'][0]['mainEntity']
            self.assertEqual(len(faq), 5)
            self.assertIn(SLUGS[lang], pages[landings.path(lang)])  # linked from the hub
            # Cheapest first among the examples.
            self.assertLess(html.index('UA-0007.html'), html.index('UA-0018.html'))
            self.assertEqual(html.count(landings.T[lang]['includes']), 1)

    def test_budget_groups(self):
        html = landings.pages(CARS)[SLUGS['uk']]
        self.assertIn('<b>до 12\xa0000 $</b> — 2 авто: Kia K5, Mercedes-Benz B-Class', html)
        self.assertIn('<b>від 18\xa0000 $</b> — 2 авто: Audi A6, Kia K5', html)
        self.assertNotIn('12\xa0000–18\xa0000', html)

    def test_without_cars(self):
        html = landings.pages([])[SLUGS['ru']]
        self.assertNotIn('<h2>Цены по моделям', html)
        self.assertNotIn('<h2>Примеры из каталога', html)
        self.assertEqual(html.count('<h3>'), 4)

    def test_price_page_is_never_a_kept_model_and_existing_pages_stay(self):
        pages = landings.pages(CARS)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative, html in pages.items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text(html, encoding='utf-8')
            self.assertEqual(ua_seo_index.kept_keys(root),
                             {('Mercedes-Benz', 'B-Class'), ('Kia', 'K5'), ('Audi', 'A6'), ('Hyundai', 'Sonata')})
        for lang in landings.LANGS:
            self.assertIn(landings.path(lang, landings.ORDER), pages)


if __name__ == '__main__':
    unittest.main()
