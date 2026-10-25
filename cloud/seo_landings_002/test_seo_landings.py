#!/usr/bin/env python3
"""Model page buttons open the order form with the model; other pages change only by the price page link."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

# Unchanged installed modules come from the previous releases.
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'seo_models_001'), str(HERE.parent / 'gsc_growth_001'),
                str(HERE.parent / 'ai_search_001'), str(HERE.parent / 'seo_growth_001')]

import ua_seo_landings as landings  # noqa: E402

CARS = [{'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'mileage_km': 50000,
         'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None},
        {'key': ('Hyundai', 'Sonata'), 'name': 'Hyundai Sonata 2018', 'code': 'UA-0011', 'price_usd': 11400,
         'mileage_km': 163400, 'stage': 3, 'url': 'https://www.uaart.com.ua/video/UA-0011.html', 'image': None}]
CSS_BEFORE = landings.CSS.replace(
    'table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid rgba(240,166,60,.25)}', '')
CTA = re.compile(r'<a class="cta" href="([^"]+)">')


def previous_pages(cars):
    spec = importlib.util.spec_from_file_location('previous_landings', HERE.parent / 'seo_models_001' / 'ua_seo_landings.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.pages(cars)


class OrderButtonTests(unittest.TestCase):
    def test_model_pages_choose_the_model(self):
        pages = landings.pages(CARS)
        for key, model in ((('Hyundai', 'Tucson'), 'hyundai-tucson'), (('Kia', 'K5'), 'kia-k5'),
                           (('Hyundai', 'Santa Fe'), 'hyundai-santa-fe')):
            for lang in landings.LANGS:
                html = pages[landings.path(lang, key)]
                self.assertEqual(CTA.findall(html),
                                 ['/video/podbor.html?strana=korea&amp;model=%s&amp;lang=%s' % (model, lang)])

    def test_other_buttons_unchanged(self):
        pages = landings.pages(CARS)
        for lang in landings.LANGS:
            for key in (None, landings.ORDER, landings.PRICE):
                self.assertEqual(CTA.findall(pages[landings.path(lang, key)]), ['/video/podbor.html'])
            self.assertEqual(CTA.findall(pages[landings.path(lang, landings.JAPAN)]),
                             ['/video/podbor.html?strana=japan&amp;lang=%s' % lang])


class UnchangedTests(unittest.TestCase):
    def strip(self, html):
        html = html.replace(landings.CSS, CSS_BEFORE)  # one shared rule added for the price table
        html = re.sub(r'<p><a href="/video/seo/[a-z]+/(skilky-koshtuie|skolko-stoit)-[^"]+">[^<]*</a></p>', '', html)
        return re.sub(r'<a class="cta" href="/video/podbor.html\?strana=korea&amp;model=[a-z0-9-]+&amp;lang=[a-z]+">',
                      '<a class="cta" href="/video/podbor.html">', html)

    def test_previous_pages(self):
        old, new = previous_pages(CARS), landings.pages(CARS)
        self.assertEqual(sorted(set(new) - set(old)), sorted(landings.path(lang, landings.PRICE) for lang in landings.LANGS))
        for relative, html in old.items():
            self.assertEqual(self.strip(new[relative]), html, relative)

    def test_price_table_lists_only_models_with_cars(self):
        html = landings.pages(CARS)[landings.path('uk', landings.PRICE)]
        self.assertNotIn('Tucson', html.split('<table>')[1].split('</table>')[0])


if __name__ == '__main__':
    unittest.main()
