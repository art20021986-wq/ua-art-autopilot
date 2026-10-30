#!/usr/bin/env python3
"""ua_card_lang and its job: the Ukrainian and Russian versions of a card, and their reconciliation."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import ua_card_lang as lang
import ua_card_lang_job as job

SCRIPT = ('/* x */ var dictionaries = {"ru":{"Пробіг":"Пробег"},"uk":{"Пробег":"Пробіг","Цена":"Ціна",'
          '"Двигатель":"Двигун","На весь экран":"На весь екран"},"ka":{}};\n var key = 1;')
CARD = ("<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        '<title data-ru="Kia K5 из Кореи" data-uk="Kia K5 з Кореї">Kia K5 из Кореи</title>'
        '<meta name="description" content="Купить" data-ru-content="Купить" data-uk-content="Купити">'
        '<link rel="canonical" href="https://www.uaart.com.ua/video/UA-0001.html"></head><body>'
        "<h1>Kia K5 2020</h1><dl><dt>Пробег</dt><dd>100 000 км</dd><dt>Двигатель</dt></dl>"
        "<p>обновлено 29.10.2026 02:58</p><img src='foto/UA-0001/1.jpg' alt='Kia K5 — фото 1'>"
        '<button aria-label="На весь экран">⛶</button><a href="UA-0001-diag.html">x</a><a href="#top">y</a>'
        "<script>var t = 'Пробег'; var g = [{src:'foto/UA-0001/001.jpg'}];</script></body></html>")


class TranslationTests(unittest.TestCase):
    def test_ukrainian_version(self):
        words = lang.dictionary(SCRIPT)
        pages, missing = lang.versions(CARD, 'UA-0001.html', words, 'a' * 64)
        self.assertEqual(missing, [])
        uk, ru = pages['ua/UA-0001.html'], pages['ru/UA-0001.html']
        self.assertIn('<html lang="uk">', uk)
        self.assertIn('>Kia K5 з Кореї</title>', uk)
        self.assertIn('content="Купити"', uk)
        self.assertIn('<dt>Пробіг</dt>', uk)
        self.assertIn('<dt>Двигун</dt>', uk)
        self.assertIn('<p>оновлено 29.10.2026 02:58</p>', uk)
        self.assertIn('aria-label="На весь екран"', uk)
        self.assertIn("var t = 'Пробег';", uk)  # scripts are never translated
        self.assertIn("{src:'/video/foto/UA-0001/001.jpg'}", uk)
        self.assertIn("src='/video/foto/UA-0001/1.jpg'", uk)
        self.assertIn('href="/video/UA-0001-diag.html"', uk)
        self.assertIn('href="#top"', uk)
        self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/ua/UA-0001.html">', uk)
        self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/ru/UA-0001.html">', ru)
        for page in (uk, ru):
            self.assertEqual(page.count('rel="canonical"'), 1)
            self.assertIn('hreflang="uk" href="https://www.uaart.com.ua/video/ua/UA-0001.html"', page)
            self.assertIn('hreflang="ru" href="https://www.uaart.com.ua/video/ru/UA-0001.html"', page)
            self.assertIn('hreflang="x-default" href="https://www.uaart.com.ua/video/ua/UA-0001.html"', page)
        self.assertIn('<html lang="ru">', ru)
        self.assertIn('<dt>Пробег</dt>', ru)

    def test_untranslated_phrase_stops_the_version(self):
        words = lang.dictionary(SCRIPT)
        del words['На весь экран']
        self.assertEqual(lang.versions(CARD, 'UA-0001.html', words, 'a' * 64), (None, ['На весь экран']))

    def test_only_card_names(self):
        with self.assertRaises(ValueError):
            lang.versions(CARD, 'katalog.html', {}, 'a' * 64)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root/'ua-site-languages.js').write_text(SCRIPT, encoding='utf-8')
        (self.root/'UA-0001.html').write_text(CARD, encoding='utf-8')

    def test_written_once_then_kept_then_removed(self):
        result = lang.reconcile(self.root, {'UA-0001.html'})
        self.assertEqual(result['written'], ['UA-0001.html'])
        self.assertTrue((self.root/'ua/UA-0001.html').is_file() and (self.root/'ru/UA-0001.html').is_file())
        self.assertEqual(lang.reconcile(self.root, {'UA-0001.html'})['written'], [])
        (self.root/'UA-0001.html').write_text(CARD.replace('2020', '2021'), encoding='utf-8')
        self.assertEqual(lang.reconcile(self.root, {'UA-0001.html'})['written'], ['UA-0001.html'])
        self.assertIn('Kia K5 2021', (self.root/'ua/UA-0001.html').read_text(encoding='utf-8'))
        result = lang.reconcile(self.root, set())
        self.assertEqual(result['removed'], ['ua/UA-0001.html', 'ru/UA-0001.html'])

    def test_one_broken_card_never_stops_the_others(self):
        result = lang.reconcile(self.root, {'UA-0001.html', 'UA-0002.html'})
        self.assertEqual(result['written'], ['UA-0001.html'])
        self.assertIn('UA-0002.html', result['failed'])

    def test_canonical_points_to_the_ukrainian_version_once_both_exist(self):
        self.assertEqual(lang.canonical('UA-0001.html', self.root), 'https://www.uaart.com.ua/video/UA-0001.html')
        lang.reconcile(self.root, {'UA-0001.html'})
        self.assertEqual(lang.canonical('UA-0001.html', self.root), 'https://www.uaart.com.ua/video/ua/UA-0001.html')
        self.assertEqual(lang.root_of('UA-0001.html'), Path('/home/Carix/video'))
        self.assertEqual(lang.root_of(str(self.root/'UA-0001.html')), self.root)


class JobTests(unittest.TestCase):
    def test_runs_under_the_publication_fence_and_refreshes_only_on_change(self):
        events = []

        class Fence:
            def __init__(self, timeout):
                events.append(('fence', timeout))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                events.append('released')
        modules = {'publication_fence': types.SimpleNamespace(publication_fence=Fence),
                   'ua_seo_sitemap': types.SimpleNamespace(CatalogLinks=lambda source: types.SimpleNamespace(names={'UA-0001.html'})),
                   'ua_seo_index': types.SimpleNamespace(refresh=lambda root: events.append('refresh') or {'status': 'PASS'})}
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, modules):
            root = Path(folder)
            (root/'katalog.html').write_text('x', encoding='utf-8')
            (root/'ua-site-languages.js').write_text(SCRIPT, encoding='utf-8')
            (root/'UA-0001.html').write_text(CARD, encoding='utf-8')
            self.assertEqual(job.run(root)['written'], ['UA-0001.html'])
            self.assertNotIn('seo_index', job.run(root))
        self.assertEqual(events, [('fence', 5.0), 'refresh', 'released', ('fence', 5.0), 'released'])


if __name__ == '__main__':
    unittest.main()
